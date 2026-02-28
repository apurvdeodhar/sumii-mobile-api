"""add_lawyer_firm_to_connections

Add lawyer_firm column to lawyer_connections table to persist
the law firm name for display on reload (SlideToSend component).

Revision ID: ts20260218_firm
Revises: ts20260201_msg_id
Create Date: 2026-02-18 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "ts20260218_firm"
down_revision = "ts20260201_msg_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lawyer_connections", sa.Column("lawyer_firm", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("lawyer_connections", "lawyer_firm")
