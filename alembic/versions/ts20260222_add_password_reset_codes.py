"""add password_reset_codes table

Stores 6-digit OTP codes for the new password reset flow.
Replaces JWT token links with time-limited single-use codes.

Revision ID: ts20260222_add_password_reset_codes
Revises: ts20260220_oauth
Create Date: 2026-02-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "ts20260222_otp_reset"
down_revision = "ts20260220_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_codes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_password_reset_codes_user_id", "password_reset_codes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_codes_user_id", table_name="password_reset_codes")
    op.drop_table("password_reset_codes")
