"""add_wrapup_fields_to_conversations

Revision ID: 8d009a31dd83
Revises: e2a2d2bae412
Create Date: 2026-01-02 21:53:08.357381

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d009a31dd83"
down_revision: Union[str, Sequence[str], None] = "e2a2d2bae412"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add wrap-up confirmation fields to conversations table
    op.add_column("conversations", sa.Column("wrapup_confirmed", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("conversations", sa.Column("wrapup_content", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("wrapup_confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("conversations", "wrapup_confirmed_at")
    op.drop_column("conversations", "wrapup_content")
    op.drop_column("conversations", "wrapup_confirmed")
