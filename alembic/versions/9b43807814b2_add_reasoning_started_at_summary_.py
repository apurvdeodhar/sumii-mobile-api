"""Add reasoning_started_at, summary_started_at, missing_info. Rename analysis_done to reasoning_done

Revision ID: 9b43807814b2
Revises: tb1234567890
Create Date: 2026-01-18 23:43:11.701473

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b43807814b2"
down_revision: Union[str, Sequence[str], None] = "tb1234567890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Changes to conversations table:
    - Add reasoning_done (replacement for analysis_done)
    - Add reasoning_started_at (timestamp when reasoning agent started)
    - Add summary_started_at (timestamp when summary agent started)
    - Add missing_info (JSONB for tracking documents user mentioned but hasn't uploaded)
    - Drop analysis_done (renamed to reasoning_done)
    """
    # Add new columns to conversations
    op.add_column("conversations", sa.Column("reasoning_done", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("conversations", sa.Column("reasoning_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("summary_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversations", sa.Column("missing_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Migrate data from analysis_done to reasoning_done
    op.execute("UPDATE conversations SET reasoning_done = analysis_done")

    # Drop the old column
    op.drop_column("conversations", "analysis_done")


def downgrade() -> None:
    """Downgrade schema."""
    # Add back analysis_done
    op.add_column(
        "conversations",
        sa.Column("analysis_done", sa.BOOLEAN(), server_default="false", autoincrement=False, nullable=False),
    )

    # Migrate data back
    op.execute("UPDATE conversations SET analysis_done = reasoning_done")

    # Drop new columns
    op.drop_column("conversations", "missing_info")
    op.drop_column("conversations", "summary_started_at")
    op.drop_column("conversations", "reasoning_started_at")
    op.drop_column("conversations", "reasoning_done")
