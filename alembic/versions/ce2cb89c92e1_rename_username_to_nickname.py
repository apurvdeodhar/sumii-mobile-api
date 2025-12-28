"""rename_username_to_nickname

Revision ID: ce2cb89c92e1
Revises: fe8fca59e259
Create Date: 2025-12-27 23:30:46.293232

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ce2cb89c92e1"
down_revision: Union[str, Sequence[str], None] = "fe8fca59e259"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename username column to nickname in users table."""
    op.alter_column("users", "username", new_column_name="nickname")


def downgrade() -> None:
    """Rename nickname column back to username in users table."""
    op.alter_column("users", "nickname", new_column_name="username")
