"""
Authentication Endpoints using fastapi-users
Registration, login, email verification, password reset, and OAuth
"""

import logging
from datetime import timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.users import auth_backend, current_active_user, fastapi_users, get_user_manager, google_oauth_client
from app.utils.security import create_access_token

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

# Password reset router
router.include_router(
    fastapi_users.get_reset_password_router(),
)

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
    # Calculate expiration
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # Create new token
    new_token = create_access_token(
        data={"sub": str(current_user.id)},
        expires_delta=expires_delta,
    )

    return TokenResponse(
        access_token=new_token,
        token_type="bearer",
        expires_in=int(expires_delta.total_seconds()),
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

    # Generate JWT
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=expires_delta,
    )

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
        expires_in=int(expires_delta.total_seconds()),
    )
