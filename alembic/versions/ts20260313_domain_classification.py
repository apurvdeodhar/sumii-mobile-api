"""Add domain classification fields and expand legal_area enum

Expands LegalArea enum from 4 to 9 values (8 domains + Other).
Adds UserIntent enum (dispute/drafting).
Adds user_intent and classification JSONB columns to conversations.

Part of domain-aware intake architecture (Phase 1).

Revision ID: ts20260313_domain_classification
Revises: ts20260222_email_otp
Create Date: 2026-03-13
"""

import sqlalchemy as sa

from alembic import op

revision = "ts20260313_domain_classification"
down_revision = "ts20260222_email_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires COMMIT before ALTER TYPE ... ADD VALUE
    op.execute("COMMIT")

    # Expand LegalArea enum with 5 new domains
    # IMPORTANT: SQLAlchemy Enum(PythonEnum) uses .name (UPPERCASE) as DB values,
    # NOT .value. These must match the Python enum member names exactly.
    op.execute("ALTER TYPE legalarea ADD VALUE IF NOT EXISTS 'FAMILIENRECHT'")
    op.execute("ALTER TYPE legalarea ADD VALUE IF NOT EXISTS 'ERBRECHT'")
    op.execute("ALTER TYPE legalarea ADD VALUE IF NOT EXISTS 'DELIKTSRECHT'")
    op.execute("ALTER TYPE legalarea ADD VALUE IF NOT EXISTS 'SACHENRECHT'")
    op.execute("ALTER TYPE legalarea ADD VALUE IF NOT EXISTS 'GESELLSCHAFTSRECHT'")

    # Create UserIntent enum (values must match Python enum .name = UPPERCASE)
    userintent_enum = sa.Enum("DISPUTE", "DRAFTING", name="userintent")
    userintent_enum.create(op.get_bind(), checkfirst=True)

    # Add user_intent column
    op.add_column(
        "conversations",
        sa.Column("user_intent", sa.Enum("DISPUTE", "DRAFTING", name="userintent"), nullable=True),
    )

    # Add classification JSONB column (stores full Router classification result)
    op.add_column(
        "conversations",
        sa.Column("classification", sa.dialects.postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "classification")
    op.drop_column("conversations", "user_intent")

    # Drop UserIntent enum
    sa.Enum(name="userintent").drop(op.get_bind(), checkfirst=True)

    # Note: Cannot remove values from PostgreSQL enums without recreating the type.
    # The extra LegalArea values are harmless if left in place.
