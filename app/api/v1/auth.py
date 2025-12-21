"""
Authentication Endpoints using fastapi-users
Registration, login, email verification, password reset, and OAuth
"""

from fastapi import APIRouter

from app.config import settings
from app.schemas.user import UserCreate, UserRead
from app.users import auth_backend, fastapi_users, google_oauth_client

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
