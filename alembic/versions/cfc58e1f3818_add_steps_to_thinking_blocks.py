"""add_steps_to_thinking_blocks

Revision ID: cfc58e1f3818
Revises: d37b7bc7dccb
Create Date: 2026-01-25 16:43:46.769309

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfc58e1f3818"
down_revision: Union[str, Sequence[str], None] = "d37b7bc7dccb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add steps JSONB column to thinking_blocks for progressive agent step tracking."""
    # Add steps column with default empty array
    op.add_column(
        "thinking_blocks",
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    """Remove steps column from thinking_blocks."""
    op.drop_column("thinking_blocks", "steps")
