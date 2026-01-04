"""extend_pdf_url_to_2000_chars

Revision ID: a496b2854b78
Revises: 8d009a31dd83
Create Date: 2026-01-04 14:45:33.364919

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a496b2854b78"
down_revision: Union[str, Sequence[str], None] = "8d009a31dd83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend pdf_url column from VARCHAR(1000) to VARCHAR(2000).

    This fixes the StringDataRightTruncationError in production.
    ECS Fargate uses STS temporary credentials which add ~700 chars
    of URL-encoded session token to pre-signed URLs, resulting in
    URLs of ~1085 chars that exceed VARCHAR(1000).
    """
    op.alter_column(
        "summaries", "pdf_url", type_=sa.String(2000), existing_type=sa.String(1000), existing_nullable=False
    )


def downgrade() -> None:
    """Revert pdf_url column back to VARCHAR(1000)."""
    op.alter_column(
        "summaries", "pdf_url", type_=sa.String(1000), existing_type=sa.String(2000), existing_nullable=False
    )
