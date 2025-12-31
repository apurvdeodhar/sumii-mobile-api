"""add_document_ids_to_messages

Revision ID: e2a2d2bae412
Revises: ce2cb89c92e1
Create Date: 2025-12-31 03:20:47.892788

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a2d2bae412"
down_revision: Union[str, Sequence[str], None] = "ce2cb89c92e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add document_ids column to messages table."""
    op.add_column("messages", sa.Column("document_ids", postgresql.ARRAY(sa.UUID()), nullable=True))


def downgrade() -> None:
    """Remove document_ids column from messages table."""
    op.drop_column("messages", "document_ids")
