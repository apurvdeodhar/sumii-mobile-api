"""rename thinking_blocks to thinking_steps

Revision ID: ts20260201_rename
Revises: cfc58e1f3818
Create Date: 2026-02-01 17:35:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "ts20260201_rename"
down_revision = "0c8d9e1f2a3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename table
    op.rename_table("thinking_blocks", "thinking_steps")

    # Rename indexes
    op.execute("ALTER INDEX ix_thinking_blocks_conversation RENAME TO ix_thinking_steps_conversation")
    op.execute("ALTER INDEX ix_thinking_blocks_created RENAME TO ix_thinking_steps_created")


def downgrade() -> None:
    # Rename table back
    op.rename_table("thinking_steps", "thinking_blocks")

    # Rename indexes back
    op.execute("ALTER INDEX ix_thinking_steps_conversation RENAME TO ix_thinking_blocks_conversation")
    op.execute("ALTER INDEX ix_thinking_steps_created RENAME TO ix_thinking_blocks_created")
