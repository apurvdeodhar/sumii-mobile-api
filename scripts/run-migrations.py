#!/usr/bin/env python3
"""
Run Alembic Migrations Script (Python)
Runs migrations on both development and test databases using .env configuration

This script properly uses Pydantic Settings to load .env file.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings  # noqa: E402


def run_migrations(database_name: str = "sumii_dev"):
    """Run Alembic migrations on specified database"""
    import subprocess

    # Get base URL from settings (reads from .env)
    original_url = settings.DATABASE_URL
    new_url = original_url.replace("sumii_dev", database_name)

    # Create environment with overridden DATABASE_URL
    # Alembic env.py will check os.getenv("DATABASE_URL") first
    env = os.environ.copy()
    env["DATABASE_URL"] = new_url

    print(f"📊 Migrating {database_name} database...")
    print(f"   URL: {new_url.replace('postgres:postgres@', 'postgres:***@')}")

    # Run alembic upgrade head with environment override
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=project_root,
        env=env,
    )

    if result.returncode != 0:
        print(f"❌ Migration failed for {database_name}")
        sys.exit(1)

    print(f"✅ {database_name} migration complete!")


def main():
    """Main entry point"""
    print("🔄 Running Alembic migrations...")
    print(f"📄 Using .env file: {project_root / '.env'}")
    print(f"📄 Current DATABASE_URL: {settings.DATABASE_URL.replace('postgres:postgres@', 'postgres:***@')}")
    print()

    # Run migrations on development database
    run_migrations("sumii_dev")

    print()

    # Run migrations on test database
    run_migrations("sumii_test")

    print()
    print("✅ All migrations complete!")


if __name__ == "__main__":
    main()
