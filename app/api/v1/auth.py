"""
Authentication Endpoints using fastapi-users
Registration, login, email verification, password reset, and OAuth
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.email_verification_code import EmailVerificationCode
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.users import (
    auth_backend,
    current_active_user,
    fastapi_users,
    get_jwt_strategy,
    get_user_manager,
    google_oauth_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# JWT Authentication router (login/logout)
# Note: fastapi-users creates /login endpoint, we want /api/v1/auth/login
# So we include it without prefix (auth router already has /api/v1/auth prefix from main.py)
router.include_router(
    fastapi_users.get_auth_router(auth_backend, requires_verification=True),  # Require email verification to login
)

# Registration router
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
)

# Email verification router
router.include_router(
    fastapi_users.get_verify_router(UserRead),
)

# Password reset router — replaced by custom OTP endpoints below (/forgot-password, /reset-password)

# Google OAuth router (if configured)
if google_oauth_client:
    router.include_router(
        fastapi_users.get_oauth_router(google_oauth_client, auth_backend, settings.SECRET_KEY),
        prefix="/google",
    )


# --- Custom Refresh Token Endpoint ---


class TokenResponse(BaseModel):
    """Token response matching login endpoint format"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until expiration


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: Annotated[User, Depends(current_active_user)],
) -> TokenResponse:
    """
    Refresh access token for authenticated user.

    Call this endpoint before token expires to get a fresh token.
    Requires valid (not expired) access token in Authorization header.

    Returns new access token with full TTL (7 days).
    """
    # Create new token using fastapi-users' strategy (includes aud: "fastapi-users:auth")
    strategy = get_jwt_strategy()
    new_token = await strategy.write_token(current_user)

    return TokenResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# --- Mobile Google OAuth Endpoint ---


class GoogleMobileAuthRequest(BaseModel):
    """Request body for mobile Google OAuth"""

    id_token: str


@router.post("/google/mobile", response_model=TokenResponse)
async def google_mobile_auth(
    body: GoogleMobileAuthRequest,
    user_manager=Depends(get_user_manager),
) -> TokenResponse:
    """
    Mobile Google OAuth — accepts a Google ID token from expo-auth-session,
    verifies it with Google, creates or authenticates the user, and returns a JWT.

    The mobile app uses expo-auth-session to get a Google ID token directly,
    then sends it here instead of using the web-based redirect flow.
    """
    # Verify Google ID token
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": body.id_token},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google ID token")

    google_user = resp.json()
    google_email = google_user.get("email")
    if not google_email:
        raise HTTPException(status_code=401, detail="Google token missing email")

    # Verify audience matches our Google Client ID
    if settings.GOOGLE_CLIENT_ID and google_user.get("aud") != settings.GOOGLE_CLIENT_ID:
        logger.warning(f"Google OAuth audience mismatch: {google_user.get('aud')}")
        # Don't reject — mobile may use a different client ID

    # Try to find existing user or create one

    from app.database import get_db
    from app.models.oauth_account import OAuthAccount

    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        # Check if user exists by email
        existing_user = await user_manager.get_by_email(google_email)

        # Ensure user is verified (OAuth users should be)
        if not existing_user.is_verified:
            existing_user.is_verified = True
            await user_manager.user_db.update(existing_user, {"is_verified": True})

        user = existing_user
    except Exception:
        # User doesn't exist — create new one
        import uuid

        from fastapi_users.password import PasswordHelper

        password_helper = PasswordHelper()
        random_password = password_helper.hash(uuid.uuid4().hex)

        user_create = UserCreate(
            email=google_email,
            password=random_password,
        )
        user = await user_manager.create(user_create, safe=True)

        # Mark as verified (Google already verified email)
        user.is_verified = True
        await user_manager.user_db.update(user, {"is_verified": True})

        # Create OAuth account link
        oauth_account = OAuthAccount(
            user_id=user.id,
            oauth_name="google",
            account_id=google_user.get("sub", ""),
            account_email=google_email,
            access_token=body.id_token,
        )
        db.add(oauth_account)
        await db.commit()

        logger.info(f"Created Google OAuth user: {google_email}")
    finally:
        await db_gen.aclose()

    # Generate JWT using fastapi-users' strategy (includes aud: "fastapi-users:auth")
    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)

    # Send login alert (non-blocking)
    try:
        from app.services.email_service import EmailService

        email_service = EmailService()
        await email_service.send_login_alert_email(user.email, language=user.language or "de")
    except Exception as e:
        logger.warning(f"Failed to send login alert for Google OAuth user: {e}")

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# --- OTP Password Reset Endpoints ---


class ForgotPasswordOTPRequest(BaseModel):
    email: EmailStr


class ResetPasswordOTPRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=8)


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/forgot-password", status_code=202)
async def forgot_password_otp(
    body: ForgotPasswordOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Request a 6-digit OTP code for password reset.

    Always returns 202 — no email enumeration (same response whether email exists or not).
    OTP code is valid for OTP_EXPIRE_MINUTES (default 10). Previous unused codes are invalidated.
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.unique().scalar_one_or_none()
    if not user:
        return  # 202 — don't reveal whether email exists

    # Invalidate all previous unused codes for this user
    await db.execute(
        delete(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.used == False,  # noqa: E712
        )
    )

    code = PasswordResetCode.generate_code()
    reset_code = PasswordResetCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(reset_code)
    await db.commit()

    try:
        from app.services.email_service import EmailService

        email_service = EmailService()
        await email_service.send_password_reset_otp_email(user.email, code, language=user.language or "de")
    except Exception as e:
        logger.warning(f"Failed to send OTP email to {user.email}: {e}")


@router.post("/verify-reset-code", status_code=200)
async def verify_reset_code(
    body: VerifyResetCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Verify that a password reset OTP code is valid without consuming it.

    Returns 200 if code is valid, 400 if invalid/expired.
    The code is NOT marked as used — that happens in /reset-password.
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.unique().scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid code")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.code == body.code,
            PasswordResetCode.used == False,  # noqa: E712
            PasswordResetCode.expires_at > now,
        )
    )
    reset_code = result.scalar_one_or_none()
    if not reset_code:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    # Code is valid — NOT marking as used (that happens in /reset-password)


@router.post("/reset-password")
async def reset_password_otp(
    body: ResetPasswordOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Reset password using a 6-digit OTP code.

    Returns 400 for invalid/expired/already-used codes.
    """
    from fastapi_users.password import PasswordHelper

    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.unique().scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid code")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PasswordResetCode).where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.code == body.code,
            PasswordResetCode.used == False,  # noqa: E712
            PasswordResetCode.expires_at > now,
        )
    )
    reset_code = result.scalar_one_or_none()
    if not reset_code:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    password_helper = PasswordHelper()
    user.hashed_password = password_helper.hash(body.password)
    reset_code.used = True
    await db.commit()


# --- Email Verification OTP Endpoints ---


class RequestVerificationOTPRequest(BaseModel):
    email: EmailStr


class VerifyEmailOTPRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.post("/request-verification-otp", status_code=202)
async def request_verification_otp(
    body: RequestVerificationOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Resend email verification OTP.

    Always returns 202 — no email enumeration. No-op for already-verified users.
    OTP valid for OTP_EXPIRE_MINUTES (default 10). Previous unused codes are invalidated.
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.unique().scalar_one_or_none()
    if not user or user.is_verified:
        return  # 202 — don't reveal whether email exists or is already verified

    # Invalidate all previous unused codes
    await db.execute(
        delete(EmailVerificationCode).where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.used.is_(False),
        )
    )

    code = EmailVerificationCode.generate_code()
    verification = EmailVerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
    )
    db.add(verification)
    await db.commit()

    try:
        from app.services.email_service import EmailService

        email_service = EmailService()
        await email_service.send_email_verification_otp_email(user.email, code, language=user.language or "de")
    except Exception as e:
        logger.warning(f"Failed to resend verification OTP to {user.email}: {e}")


class VerifyEmailTokenResponse(BaseModel):
    """Token response for auto-login after email verification"""

    access_token: str
    token_type: str = "bearer"


@router.post("/verify-email-otp", response_model=VerifyEmailTokenResponse)
async def verify_email_otp(
    body: VerifyEmailOTPRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyEmailTokenResponse:
    """
    Verify email address using 6-digit OTP code.

    Marks user as verified and returns a JWT for immediate auto-login.
    Returns 400 for invalid/expired codes.
    """
    result = await db.execute(select(User).where(User.email == body.email.lower()))
    user = result.unique().scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid code")

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EmailVerificationCode).where(
            EmailVerificationCode.user_id == user.id,
            EmailVerificationCode.code == body.code,
            EmailVerificationCode.used.is_(False),
            EmailVerificationCode.expires_at > now,
        )
    )
    verification = result.scalar_one_or_none()
    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Mark verified + consume code atomically
    user.is_verified = True
    verification.used = True
    await db.commit()
    await db.refresh(user)

    # Generate JWT using fastapi-users' strategy (includes aud: "fastapi-users:auth")
    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)

    return VerifyEmailTokenResponse(access_token=token)
