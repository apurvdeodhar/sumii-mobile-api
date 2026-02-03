"""add_document_tracker_to_conversations

Revision ID: d37b7bc7dccb
Revises: 9b43807814b2
Create Date: 2026-01-24 00:28:47.403051

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d37b7bc7dccb"
down_revision: Union[str, Sequence[str], None] = "9b43807814b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add document_tracker JSONB column to conversations table."""
    op.add_column(
        "conversations", sa.Column("document_tracker", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    """Remove document_tracker column from conversations table."""
    op.drop_column("conversations", "document_tracker")
