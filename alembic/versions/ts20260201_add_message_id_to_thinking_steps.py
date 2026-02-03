"""add_message_id_to_thinking_steps

Add message_id FK to thinking_steps table to associate each ThinkingSteps
with the user message that triggered it. Enables per-message ThinkingBubble
rendering in the mobile app.

Revision ID: ts20260201_msg_id
Revises: ts20260201_rename
Create Date: 2026-02-01 18:10:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "ts20260201_msg_id"
down_revision = "ts20260201_rename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add message_id column to thinking_steps table."""
    # Add nullable message_id column
    op.add_column(
        "thinking_steps",
        sa.Column("message_id", UUID(as_uuid=True), nullable=True),
    )

    # Create foreign key to messages table
    op.create_foreign_key(
        "fk_thinking_steps_message_id",
        "thinking_steps",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Create index for efficient lookups
    op.create_index(
        "ix_thinking_steps_message",
        "thinking_steps",
        ["message_id"],
    )


def downgrade() -> None:
    """Remove message_id column from thinking_steps table."""
    op.drop_index("ix_thinking_steps_message", table_name="thinking_steps")
    op.drop_constraint("fk_thinking_steps_message_id", "thinking_steps", type_="foreignkey")
    op.drop_column("thinking_steps", "message_id")
