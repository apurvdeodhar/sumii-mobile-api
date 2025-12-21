"""Add fastapi-users required fields (is_active, is_verified, is_superuser)

Revision ID: f8e9d7c6b5a4
Revises: 452ec56963cf
Create Date: 2025-01-27 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8e9d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "452ec56963cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add fastapi-users required boolean fields"""
    # Add fastapi-users required fields with server defaults for existing rows
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema - Remove fastapi-users fields"""
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_active")
