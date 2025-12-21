"""
Pytest Configuration and Fixtures
Shared test fixtures for database, client, and test data
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import Base, get_db
from app.main import app

# Test database URL (use separate test database)
# Ensure we keep the async driver (postgresql+asyncpg://)
TEST_DATABASE_URL = settings.DATABASE_URL.replace("sumii_dev", "sumii_test")
if "+asyncpg" not in TEST_DATABASE_URL and "postgresql://" in TEST_DATABASE_URL:
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create a test database engine with clean schema using Alembic migrations"""
    import os
    import subprocess
    from pathlib import Path

    from sqlalchemy import text

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

    # Ensure clean state: drop and recreate schema
    async with engine.begin() as conn:
        # Drop all objects (tables, indexes, etc.) using CASCADE
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

    # Use Alembic migrations instead of create_all() to avoid duplicate index errors
    # Convert async URL to sync for Alembic
    sync_db_url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    # Run Alembic migrations using venv Python
    env = os.environ.copy()
    env["DATABASE_URL"] = sync_db_url

    # Get project root directory (parent of tests/)
    project_root = Path(__file__).resolve().parent.parent
    # Use venv Python to run alembic as a module
    venv_python = project_root / ".venv" / "bin" / "python3"

    # Fallback to system Python if venv doesn't exist (for CI/CD)
    python_cmd = str(venv_python) if venv_python.exists() else "python3"

    try:
        subprocess.run(
            [python_cmd, "-m", "alembic", "upgrade", "head"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(project_root),
        )
    except subprocess.CalledProcessError as e:
        # If migrations fail, fall back to create_all (for development)
        print(f"Alembic migration failed: {e.stderr if hasattr(e, 'stderr') else 'Unknown error'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=False)

    yield engine

    # Cleanup: drop schema completely
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    """Create a test database session"""
    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session, test_user):
    """Create a test client with overridden database dependency"""

    async def override_get_db():
        yield db_session

    from app.users import current_active_user

    async def override_current_active_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_active_user] = override_current_active_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session, test_user):
    """Async test client (alias for client fixture)"""

    async def override_get_db():
        yield db_session

    from app.users import current_active_user

    async def override_current_active_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_active_user] = override_current_active_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session):
    """Create a test user (fastapi-users compatible)"""
    from fastapi_users.password import PasswordHelper

    from app.models.user import User

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("testpass123")
    user = User(
        email="testuser@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user


@pytest_asyncio.fixture(scope="function")
async def other_user(db_session):
    """Create another test user (for authorization tests)"""
    from fastapi_users.password import PasswordHelper

    from app.models.user import User

    password_helper = PasswordHelper()
    hashed_password = password_helper.hash("testpass123")
    user = User(
        email="otheruser@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(test_user):
    """Generate auth headers with JWT token (fastapi-users format)"""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import settings

    # fastapi-users JWT format: sub contains user ID (UUID), not email
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(test_user.id), "aud": ["fastapi-users:auth"], "exp": expire}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def test_conversation(db_session, test_user):
    """Create a test conversation"""
    from app.models.conversation import Conversation, ConversationStatus

    conversation = Conversation(user_id=test_user.id, title="Test Conversation", status=ConversationStatus.ACTIVE)
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest_asyncio.fixture(scope="function")
async def other_user_conversation(db_session, other_user):
    """Create a conversation owned by another user"""
    from app.models.conversation import Conversation, ConversationStatus

    conversation = Conversation(
        user_id=other_user.id, title="Other User Conversation", status=ConversationStatus.ACTIVE
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest_asyncio.fixture(scope="function")
async def test_document(db_session, test_user, test_conversation):
    """Create a test document"""
    from app.models.document import Document, OCRStatus, UploadStatus

    document = Document(
        conversation_id=test_conversation.id,
        user_id=test_user.id,
        filename="test_document.pdf",
        file_type="application/pdf",
        file_size=1024,
        s3_key=f"users/{test_user.id}/conversations/{test_conversation.id}/documents/test-id/test_document.pdf",
        s3_url="https://s3.example.com/test-document-url",
        upload_status=UploadStatus.COMPLETED,
        ocr_status=OCRStatus.PENDING,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


@pytest_asyncio.fixture(scope="function")
async def other_user_document(db_session, other_user, other_user_conversation):
    """Create a document owned by another user"""
    from app.models.document import Document, OCRStatus, UploadStatus

    document = Document(
        conversation_id=other_user_conversation.id,
        user_id=other_user.id,
        filename="other_document.pdf",
        file_type="application/pdf",
        file_size=2048,
        s3_key=f"users/{other_user.id}/conversations/{other_user_conversation.id}/documents/other-id/other_document.pdf",
        s3_url="https://s3.example.com/other-document-url",
        upload_status=UploadStatus.COMPLETED,
        ocr_status=OCRStatus.PENDING,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document
