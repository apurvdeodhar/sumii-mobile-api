"""Add thinking_blocks table

Revision ID: tb1234567890
Revises: 8d009a31dd83
Create Date: 2026-01-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "tb1234567890"
down_revision: str | None = "93411c183e24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create thinking_blocks table
    op.create_table(
        "thinking_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_agent", sa.String(length=50), nullable=True),
        sa.Column("completed_agents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_generating_summary", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_thinking_blocks_conversation", "thinking_blocks", ["conversation_id"])
    op.create_index("ix_thinking_blocks_created", "thinking_blocks", ["created_at"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_thinking_blocks_created", table_name="thinking_blocks")
    op.drop_index("ix_thinking_blocks_conversation", table_name="thinking_blocks")

    # Drop table
    op.drop_table("thinking_blocks")
