"""OAuth Account Model - Store OAuth provider accounts linked to users

This model stores OAuth account information (Google, etc.) linked to User accounts.
Required for fastapi-users OAuth support.
"""

import uuid

from fastapi_users.db import SQLAlchemyBaseOAuthAccountTableUUID
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.database import Base


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    """OAuth Account model for storing OAuth provider accounts

    Inherits from SQLAlchemyBaseOAuthAccountTableUUID which provides:
    - id (UUID)
    - oauth_name (str) - OAuth provider name (e.g., "google")
    - access_token (str) - OAuth access token
    - expires_at (datetime | None) - Token expiration time
    - refresh_token (str | None) - OAuth refresh token
    - account_id (str) - OAuth provider account ID
    - account_email (str) - OAuth provider account email

    Note: We override user_id to point to "users.id" (not "user.id") to match
    our User model's table name.
    """

    __tablename__ = "oauth_accounts"

    # Override user_id to point to our "users" table (not "user")
    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        """Foreign key to users.id (not user.id)"""
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="cascade"),
            nullable=False,
        )
