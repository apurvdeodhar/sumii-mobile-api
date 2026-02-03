"""remove case_strength from summaries table

Revision ID: 0c8d9e1f2a3b
Revises: 702377249055
Create Date: 2026-01-25 23:21:00.000000

Note: case_strength is removed because Sumii does not make legal judgments -
lawyers assess case strength. This was intended to be removed earlier.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0c8d9e1f2a3b"
down_revision = "cfc58e1f3818"  # Point to the actual latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove case_strength column from summaries table."""
    # Drop the case_strength column - it should not exist
    # (Sumii doesn't make legal judgments, lawyers do)
    op.drop_column("summaries", "case_strength")


def downgrade() -> None:
    """Re-add case_strength column to summaries table."""
    op.add_column(
        "summaries", sa.Column("case_strength", sa.Enum("STRONG", "MEDIUM", "WEAK", name="casestrength"), nullable=True)
    )
