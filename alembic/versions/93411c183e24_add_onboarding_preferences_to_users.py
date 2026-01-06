"""add_onboarding_preferences_to_users

Revision ID: 93411c183e24
Revises: a496b2854b78
Create Date: 2026-01-06 19:26:22.497895

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "93411c183e24"
down_revision: Union[str, Sequence[str], None] = "a496b2854b78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add onboarding preference columns to users table."""
    # Add onboarding preference columns
    op.add_column("users", sa.Column("notifications_enabled", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("users", sa.Column("location_enabled", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("users", sa.Column("disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove onboarding preference columns from users table."""
    # Remove onboarding preference columns
    op.drop_column("users", "disclaimer_accepted_at")
    op.drop_column("users", "location_enabled")
    op.drop_column("users", "notifications_enabled")
