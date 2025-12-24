"""Change case_id from integer to string

Revision ID: 9a8b7c6d5e4f
Revises: 8a9b7c6d5e4f
Create Date: 2025-12-24 15:27:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a8b7c6d5e4f"
down_revision: Union[str, None] = "8a9b7c6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change case_id from INTEGER to VARCHAR(100)
    # sumii-anwalt returns string IDs like 'SUMII-068C2F84'
    op.alter_column(
        "lawyer_connections", "case_id", existing_type=sa.INTEGER(), type_=sa.String(length=100), existing_nullable=True
    )


def downgrade() -> None:
    # Change case_id back to INTEGER
    op.alter_column(
        "lawyer_connections", "case_id", existing_type=sa.String(length=100), type_=sa.INTEGER(), existing_nullable=True
    )
