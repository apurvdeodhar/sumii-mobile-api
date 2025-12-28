"""add_username_field

Revision ID: fe8fca59e259
Revises: a1b2c3d4e5f6
Create Date: 2025-12-27 21:26:06.963421

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe8fca59e259"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add username field to users table."""
    op.add_column("users", sa.Column("username", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema - remove username field from users table."""
    op.drop_column("users", "username")
