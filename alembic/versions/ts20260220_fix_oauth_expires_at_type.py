"""fix_oauth_expires_at_type

Fix oauth_accounts.expires_at column type: DateTime(timezone=True) -> Integer.
fastapi-users SQLAlchemyBaseOAuthAccountTableUUID defines expires_at as
Mapped[Optional[int]] (Integer), but the original migration created it as
DateTime. This causes DatatypeMismatchError on Google OAuth for new users.

Revision ID: ts20260220_oauth
Revises: ts20260218_firm
Create Date: 2026-02-20 11:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "ts20260220_oauth"
down_revision = "ts20260218_firm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "oauth_accounts",
        "expires_at",
        type_=sa.Integer(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="EXTRACT(EPOCH FROM expires_at)::integer",
    )


def downgrade() -> None:
    op.alter_column(
        "oauth_accounts",
        "expires_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.Integer(),
        existing_nullable=True,
        postgresql_using="to_timestamp(expires_at)",
    )
