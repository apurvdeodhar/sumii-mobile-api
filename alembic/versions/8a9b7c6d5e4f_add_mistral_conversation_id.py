"""add mistral_conversation_id to conversations

Revision ID: 8a9b7c6d5e4f
Revises: fa780bfb9a37
Create Date: 2025-12-23 18:53:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a9b7c6d5e4f"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add mistral_conversation_id column for context persistence
    op.add_column("conversations", sa.Column("mistral_conversation_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    # Remove mistral_conversation_id column
    op.drop_column("conversations", "mistral_conversation_id")
