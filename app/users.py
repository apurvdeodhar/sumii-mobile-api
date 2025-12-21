"""FastAPI Users Configuration

Sets up user management, authentication, and OAuth with fastapi-users library.
"""

import uuid

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.oauth_account import OAuthAccount
from app.models.user import User

# OAuth imports (conditional)
try:
    from httpx_oauth.clients.google import GoogleOAuth2
except ImportError:
    GoogleOAuth2 = None


# Initialize OAuth client if credentials are provided
google_oauth_client = None
if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
    if GoogleOAuth2:
        google_oauth_client = GoogleOAuth2(
            settings.GOOGLE_CLIENT_ID,
            settings.GOOGLE_CLIENT_SECRET,
        )
    else:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("Google OAuth credentials provided but httpx-oauth not installed")


async def get_user_db(session: AsyncSession = Depends(get_db)) -> SQLAlchemyUserDatabase[User, uuid.UUID]:
    """Database adapter for fastapi-users with OAuth support"""
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """User manager with AWS SES email integration"""

    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY

    async def on_after_register(self, user: User, request: Request | None = None):
        """Called after user registration"""
        # Email verification will be sent via on_after_request_verify
        pass

    async def on_after_forgot_password(self, user: User, token: str, request: Request | None = None):
        """Send password reset email via AWS SES"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        await email_service.send_password_reset_email(user.email, token)

    async def on_after_request_verify(self, user: User, token: str, request: Request | None = None):
        """Send email verification link via AWS SES"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        await email_service.send_verification_email(user.email, token)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
) -> BaseUserManager[User, uuid.UUID]:
    """Dependency to get user manager"""
    yield UserManager(user_db)


# JWT Authentication Backend
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/login")


def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    """JWT authentication strategy"""
    return JWTStrategy(
        secret=settings.SECRET_KEY,
        lifetime_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPI Users instance
fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# Dependency for authenticated routes
current_active_user = fastapi_users.current_user(active=True)
