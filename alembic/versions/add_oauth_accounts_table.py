"""Add oauth_accounts table for OAuth support

Revision ID: a9b8c7d6e5f4
Revises: f8e9d7c6b5a4
Create Date: 2025-01-27 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f8e9d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create oauth_accounts table for fastapi-users OAuth support"""
    op.create_table(
        "oauth_accounts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("oauth_name", sa.String(length=100), nullable=False),
        sa.Column("access_token", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token", sa.String(), nullable=True),
        sa.Column("account_id", sa.String(), nullable=False),
        sa.Column("account_email", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("oauth_name", "account_id", name="uq_oauth_account"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema - Drop oauth_accounts table"""
    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")
