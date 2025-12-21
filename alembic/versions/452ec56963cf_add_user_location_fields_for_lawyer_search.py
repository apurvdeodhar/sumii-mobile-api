"""Add user location fields for lawyer search

Revision ID: a1b2c3d4e5f6
Revises: 20668ac8d9fb
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "452ec56963cf"
down_revision: Union[str, Sequence[str], None] = "702377249055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add location fields for lawyer search
    op.add_column("users", sa.Column("latitude", sa.String(), nullable=True))
    op.add_column("users", sa.Column("longitude", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove location fields
    op.drop_column("users", "longitude")
    op.drop_column("users", "latitude")
