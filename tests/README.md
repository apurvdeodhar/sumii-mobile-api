# Test Documentation - Sumii Mobile API

## 📋 Table of Contents

1. [Test-Driven Development (TDD) Guidelines](#test-driven-development-tdd-guidelines)
2. [Test Structure](#test-structure)
3. [Test Categories](#test-categories)
4. [Running Tests](#running-tests)
5. [Test Coverage](#test-coverage)
6. [Writing Tests](#writing-tests)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## 🎯 Test-Driven Development (TDD) Guidelines

### What is TDD?

**Test-Driven Development (TDD)** is a development approach where you:

1. **Write a failing test first** (Red)
2. **Write minimal code to make it pass** (Green)
3. **Refactor the code** (Refactor)
4. **Repeat**

### TDD Workflow

```
┌─────────────────────────────────────────────────────────┐
│ 1. RED: Write a failing test                            │
│    - Test should fail for the right reason              │
│    - Test should be specific and focused                │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 2. GREEN: Write minimal code to pass                    │
│    - Don't over-engineer                                │
│    - Make the test pass, nothing more                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ 3. REFACTOR: Improve code quality                       │
│    - Clean up, optimize, improve readability            │
│    - Ensure all tests still pass                         │
└─────────────────────────────────────────────────────────┘
                        ↓
                    REPEAT
```

### TDD Rules for Sumii

1. **Always write tests first** before implementing features
2. **Run tests frequently** (after each small change)
3. **Keep tests fast** (unit tests should run in < 1 second)
4. **Keep tests isolated** (no dependencies between tests)
5. **Mock external dependencies** (S3, Mistral AI, database)
6. **Aim for 80%+ code coverage**
7. **Never commit code without passing tests**

### TDD Example

**Scenario:** Adding a new endpoint to get user profile

```python
# Step 1: RED - Write failing test
# tests/unit/test_user_profile.py
@pytest.mark.unit
class TestUserProfile:
    @pytest.mark.asyncio
    async def test_get_user_profile(self, async_client, auth_headers):
        """Test getting user profile returns correct data"""
        response = await async_client.get("/api/v1/users/profile", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "created_at" in data
        # This test will FAIL because endpoint doesn't exist yet

# Step 2: GREEN - Write minimal code
# app/api/v1/users.py
@router.get("/profile")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    return {"email": current_user.email, "created_at": current_user.created_at}

# Step 3: REFACTOR - Improve code
# Add validation, error handling, etc.
# Ensure all tests still pass
```

---

## 📁 Test Structure

```
tests/
├── conftest.py              # Shared pytest fixtures
├── fixtures.py              # Test constants and shared data
├── unit/                    # Unit tests (fast, isolated, mocked)
│   ├── test_auth.py
│   ├── test_documents.py
│   └── test_summaries.py
├── integration/             # Integration tests (multiple components)
│   ├── test_integration.py
│   ├── test_websocket.py
│   ├── test_phase3_orchestration.py
│   ├── test_agents_library_integration.py
│   └── test_document_library.py
├── e2e/                     # End-to-end tests (full workflows)
│   └── test_e2e_complete_flow.py
├── manual/                  # Manual test scripts (not automated)
│   └── manual_test_websocket.py
└── docs/                    # Test documentation (this file)
    └── README.md
```

---

## 🏷️ Test Categories

### Unit Tests (`tests/unit/`)

**Purpose:** Test individual components in isolation

**Characteristics:**
- ✅ Fast (< 1 second per test)
- ✅ Isolated (no external dependencies)
- ✅ Mocked dependencies (S3, Mistral AI, database)
- ✅ Can run without Docker services
- ✅ High coverage of business logic

**Example:**
```python
# tests/unit/test_auth.py
@pytest.mark.unit
class TestUserRegistration:
    @pytest.mark.asyncio
    async def test_register_new_user(self, client: AsyncClient):
        """Test successful user registration"""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@sumii.de", "password": "TestPassword123!"},
        )
        assert response.status_code == 201
```

**Run unit tests:**
```bash
pytest tests/unit/ -v
pytest -m unit -v  # Using marker
```

### Integration Tests (`tests/integration/`)

**Purpose:** Test multiple components working together

**Characteristics:**
- ⚠️ Slower (1-5 seconds per test)
- ⚠️ **REQUIRES Docker services running** (PostgreSQL, backend)
- ⚠️ May require external API keys (Mistral AI)
- ✅ Test real interactions between components
- ✅ Test database operations
- ✅ Test WebSocket connections

**⚠️ IMPORTANT:** Integration tests will **FAIL** if the backend is not running!

**Example:**
```python
# tests/integration/test_integration.py
@pytest.mark.integration
@pytest.mark.requires_services
class TestUserRegistration:
    def test_register_new_user(self):
        """Test user registration with real database"""
        response = requests.post(
            "http://localhost:8000/api/v1/auth/register",
            json={"email": "test@sumii.de", "password": "TestPassword123!"},
        )
        assert response.status_code == 201
```

**Run integration tests:**
```bash
# 1. Start services FIRST (required!)
docker-compose up -d

# 2. Wait for backend to be ready
curl http://localhost:8000/health  # Should return {"status": "healthy"}

# 3. Run integration tests
pytest tests/integration/ -v
pytest -m integration -v  # Using marker
```

**Expected failures if backend not running:**
- `Connection refused` errors
- `HTTP 403` errors (WebSocket authentication)
- `HTTP 500` errors (service unavailable)

### E2E Tests (`tests/e2e/`)

**Purpose:** Test complete user workflows from start to finish

**Characteristics:**
- ⚠️ Slowest (5-30 seconds per test)
- ⚠️ **REQUIRES all services running** (PostgreSQL, backend, WebSocket)
- ⚠️ **REQUIRES external API keys** (Mistral AI)
- ✅ Test real user scenarios
- ✅ Test complete workflows
- ✅ Validate system behavior

**⚠️ IMPORTANT:** E2E tests will **FAIL** if services are not running or API keys are missing!

**Example:**
```python
# tests/e2e/test_e2e_complete_flow.py
@pytest.mark.e2e
@pytest.mark.requires_services
@pytest.mark.requires_api
def test_complete_user_flow():
    """Test complete flow: register → login → create conversation → chat"""
    # 1. Register user
    # 2. Login
    # 3. Create conversation
    # 4. Connect via WebSocket
    # 5. Send message
    # 6. Receive AI response
    # 7. Generate summary
```

**Run E2E tests:**
```bash
# 1. Start all services FIRST (required!)
docker-compose up -d

# 2. Wait for backend to be ready
curl http://localhost:8000/health  # Should return {"status": "healthy"}

# 3. Set API keys (required!)
export MISTRAL_API_KEY=your-key-here

# 4. Run E2E tests
pytest tests/e2e/ -v
pytest -m e2e -v  # Using marker
```

**Expected failures if services not running:**
- `Connection refused` errors
- `HTTP 403` errors (WebSocket authentication)
- `HTTP 500` errors (service unavailable)
- `ImportError` or `AttributeError` (missing dependencies)

---

## 🚀 Running Tests

### Quick Start

**⚠️ IMPORTANT:** Integration and E2E tests require a running backend!

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run unit tests (fast, no services needed)
pytest -m unit -v              # ✅ 40 tests, all pass (no backend needed)

# 3. Run integration tests (requires backend)
docker-compose up -d           # Start services first!
curl http://localhost:8000/health  # Verify backend is ready
pytest -m integration -v      # ⚠️ Will fail if backend not running

# 4. Run E2E tests (requires backend + API keys)
docker-compose up -d           # Start services first!
export MISTRAL_API_KEY=your-key
pytest -m e2e -v               # ⚠️ Will fail if services/keys missing

# 5. Run all tests (requires services)
docker-compose up -d
pytest -v
```

**See [tests/docs/TEST_STATUS.md](docs/TEST_STATUS.md) for detailed test status and requirements.**

### Common Commands

```bash
# Run all tests with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_auth.py -v

# Run specific test class
pytest tests/unit/test_auth.py::TestUserRegistration -v

# Run specific test function
pytest tests/unit/test_auth.py::TestUserRegistration::test_register_new_user -v

# Run tests matching pattern
pytest -k "login" -v

# Run tests in parallel (if pytest-xdist installed)
pytest -n 4 -v

# Stop at first failure
pytest -x -v

# Run only failed tests from last run
pytest --lf -v

# Show print statements
pytest -s -v

# Show local variables on failure
pytest -l -v
```

### Running Tests by Category

```bash
# Unit tests (fast, no services needed)
pytest tests/unit/ -v

# Integration tests (requires Docker services)
docker-compose up -d
pytest tests/integration/ -v

# E2E tests (requires all services + API keys)
docker-compose up -d
export MISTRAL_API_KEY=your-key
pytest tests/e2e/ -v

# Skip slow tests
pytest -m "not slow" -v

# Skip tests requiring API keys
pytest -m "not requires_api" -v
```

---

## 📊 Test Coverage

### View Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Open in browser
open htmlcov/index.html

# Terminal coverage report
pytest --cov=app --cov-report=term
```

### Coverage Goals

- **Unit Tests:** 80%+ coverage of business logic
- **Integration Tests:** 60%+ coverage of API endpoints
- **E2E Tests:** 40%+ coverage of critical workflows

### Coverage Configuration

Coverage is configured in `pytest.ini`:

```ini
[coverage:run]
source = app
omit =
    */tests/*
    */alembic/*
    */__pycache__/*
    */.venv/*
```

---

## ✍️ Writing Tests

### Test File Structure

```python
"""
Test Description (Unit/Integration/E2E Tests)

Brief description of what these tests cover.
"""

import pytest
from httpx import AsyncClient

# Mark test category
pytestmark = pytest.mark.unit  # or integration, e2e


class TestFeatureName:
    """Test class for FeatureName"""

    @pytest.mark.asyncio
    async def test_specific_behavior(self, async_client: AsyncClient):
        """Test description"""
        # Arrange
        # Act
        # Assert
        pass
```

### Using Fixtures

```python
# Use shared fixtures from conftest.py
@pytest.mark.asyncio
async def test_example(self, async_client, auth_headers, test_user, test_conversation):
    """Test using fixtures"""
    response = await async_client.get(
        "/api/v1/conversations",
        headers=auth_headers
    )
    assert response.status_code == 200
```

### Using Test Constants

```python
# Use constants from fixtures.py instead of hardcoding
from tests.fixtures import TEST_USER_EMAIL, TEST_USER_PASSWORD

@pytest.mark.asyncio
async def test_login(self, async_client):
    """Test login using shared constants"""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD}
    )
    assert response.status_code == 200
```

### Mocking External Dependencies

```python
# Mock S3 service
from app.main import app
from app.services.s3_service import get_s3_service

mock_s3 = MagicMock()
mock_s3.upload_document.return_value = ("s3_key", "https://s3.example.com/url")

def override_get_s3_service():
    return mock_s3

app.dependency_overrides[get_s3_service] = override_get_s3_service

try:
    # Your test code here
    pass
finally:
    app.dependency_overrides.pop(get_s3_service, None)
```

---

## ✅ Best Practices

### DO ✅

- ✅ Write tests first (TDD)
- ✅ Use descriptive test names (`test_register_user_with_duplicate_email`)
- ✅ Test both success and error cases
- ✅ Keep tests simple and focused (one thing per test)
- ✅ Use fixtures for shared setup
- ✅ Mock external dependencies in unit tests
- ✅ Use test constants from `fixtures.py`
- ✅ Clean up after tests (use `finally` blocks)
- ✅ Run tests before committing
- ✅ Aim for 80%+ code coverage

### DON'T ❌

- ❌ Hardcode secrets or API keys (use environment variables)
- ❌ Make tests depend on each other
- ❌ Test external libraries (pytest, requests, etc.)
- ❌ Skip writing tests because "it works locally"
- ❌ Commit code without running tests
- ❌ Use real API keys in tests (use mocks or test keys)
- ❌ Leave test data in production database
- ❌ Write tests that are too slow (> 5 seconds for unit tests)

---

## 🔒 Security in Tests

### Never Hardcode Secrets

```python
# ❌ BAD
API_KEY = "sk-1234567890abcdef"

# ✅ GOOD
from app.config import settings
api_key = settings.MISTRAL_API_KEY  # From .env file
```

### Test Passwords

Test passwords in `fixtures.py` are **ONLY for test databases**:
- Never used in production
- Only valid in test environment
- Documented as test-only

```python
# tests/fixtures.py
TEST_USER_PASSWORD = "TestPassword123!"  # Test-only password, never used in production
```

---

## 🐛 Troubleshooting

### Issue: "Connection refused" or "HTTP 403" in integration/E2E tests

**Cause:** Backend services are not running

**Solution:**
```bash
# 1. Start services
docker-compose up -d

# 2. Wait for backend to be ready (check health endpoint)
curl http://localhost:8000/health
# Should return: {"status": "healthy", "service": "sumii-mobile-api", ...}

# 3. Then run tests
pytest tests/integration/ -v
pytest tests/e2e/ -v
```

**Note:** Integration and E2E tests **require** a running backend. These failures are **expected** if services are not running.

### Issue: "ModuleNotFoundError" in tests

**Solution:**
```bash
# Install test dependencies
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Issue: Tests pass locally but fail in CI

**Causes:**
- Different environment variables
- Race conditions
- Database not properly reset

**Solutions:**
- Use fixtures for consistent setup
- Add delays for async operations
- Ensure database is clean before tests

### Issue: Slow tests

**Solutions:**
```bash
# Run only fast unit tests
pytest tests/unit/ -v

# Skip slow tests
pytest -m "not slow" -v

# Run tests in parallel
pytest -n 4 -v
```

---

## 📚 Additional Resources

- **Pytest Documentation:** https://docs.pytest.org/
- **FastAPI Testing:** https://fastapi.tiangolo.com/tutorial/testing/
- **TDD Best Practices:** https://testdriven.io/test-driven-development/
- **Python Testing Guide:** https://realpython.com/python-testing/

---

## 📝 Test Checklist

Before committing code, ensure:

- [ ] All tests pass (`pytest -v`)
- [ ] New features have tests
- [ ] Test coverage is 80%+ for new code
- [ ] No hardcoded secrets in tests
- [ ] Tests are properly categorized (unit/integration/e2e)
- [ ] Tests use fixtures and constants from `fixtures.py`
- [ ] External dependencies are mocked in unit tests
- [ ] Integration tests have `@pytest.mark.requires_services` if needed
- [ ] E2E tests have `@pytest.mark.requires_api` if needed

---

**Last Updated:** 2025-01-27
**Test Structure:** Unit / Integration / E2E
**Coverage Goal:** 80%+ for unit tests
