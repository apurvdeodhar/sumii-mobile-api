"""Add user profile fields for claimant info

Revision ID: a1b2c3d4e5f6
Revises: 9a8b7c6d5e4f
Create Date: 2025-12-24 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9a8b7c6d5e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Personal details (for Anspruchsteller section)
    op.add_column("users", sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("address_street", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("address_city", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("address_postal_code", sa.String(length=20), nullable=True))

    # Legal insurance details (for Rechtsschutzversicherung section)
    op.add_column("users", sa.Column("legal_insurance", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("insurance_company", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("insurance_number", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "insurance_number")
    op.drop_column("users", "insurance_company")
    op.drop_column("users", "legal_insurance")
    op.drop_column("users", "address_postal_code")
    op.drop_column("users", "address_city")
    op.drop_column("users", "address_street")
    op.drop_column("users", "phone")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
