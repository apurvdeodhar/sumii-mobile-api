"""
Authentication Endpoints using fastapi-users
Registration, login, email verification, password reset, and OAuth
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserRead
from app.users import auth_backend, current_active_user, fastapi_users, google_oauth_client
from app.utils.security import create_access_token

router = APIRouter(tags=["auth"])

# JWT Authentication router (login/logout)
# Note: fastapi-users creates /login endpoint, we want /api/v1/auth/login
# So we include it without prefix (auth router already has /api/v1/auth prefix from main.py)
router.include_router(
    fastapi_users.get_auth_router(auth_backend, requires_verification=False),  # Allow unverified users to login
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
