# Test Organization Summary

## Test Structure

```
tests/
├── conftest.py                    # Shared pytest fixtures
├── fixtures.py                   # Test constants and shared data
├── unit/                         # Unit tests (fast, isolated, mocked)
│   ├── test_auth.py             # Authentication unit tests
│   ├── test_documents.py        # Document API unit tests
│   └── test_summaries.py        # Summary API unit tests
├── integration/                  # Integration tests (multiple components)
│   ├── test_integration.py      # HTTP endpoint integration tests
│   ├── test_websocket.py        # WebSocket integration tests
│   ├── test_phase3_orchestration.py  # Agent orchestration tests
│   ├── test_agents_library_integration.py  # Agent library tests
│   └── test_document_library.py # Document library service tests
├── e2e/                          # End-to-end tests (complete workflows)
│   └── test_e2e_complete_flow.py  # Complete user flow E2E tests
├── manual/                       # Manual test scripts (not automated)
│   └── manual_test_websocket.py
└── docs/                         # Test documentation
    ├── test_organization.md      # This file
    └── test_summary.md           # Test reorganization summary
└── README.md                     # Comprehensive testing guide (main)
```

## Test Categories

### Unit Tests (`tests/unit/`)

**Purpose:** Test individual components in isolation

**Files:**
- `test_auth.py` - Authentication endpoints (register, login, JWT)
- `test_documents.py` - Document upload, retrieval, deletion
- `test_summaries.py` - Summary generation and retrieval

**Characteristics:**
- ✅ Fast (< 1 second per test)
- ✅ Isolated (no external dependencies)
- ✅ Mocked dependencies (S3, Mistral AI, database)
- ✅ Can run without Docker services
- ✅ High coverage of business logic

**Run:**
```bash
pytest tests/unit/ -v
pytest -m unit -v
```

### Integration Tests (`tests/integration/`)

**Purpose:** Test multiple components working together

**Files:**
- `test_integration.py` - HTTP endpoint integration tests
- `test_websocket.py` - WebSocket chat integration tests
- `test_phase3_orchestration.py` - Agent orchestration tests
- `test_agents_library_integration.py` - Agent library access tests
- `test_document_library.py` - Document library service tests

**Characteristics:**
- ⚠️ Slower (1-5 seconds per test)
- ⚠️ May require Docker services (PostgreSQL, backend)
- ⚠️ May require external API keys (Mistral AI)
- ✅ Test real interactions between components
- ✅ Test database operations
- ✅ Test WebSocket connections

**Run:**
```bash
docker-compose up -d
pytest tests/integration/ -v
pytest -m integration -v
```

### E2E Tests (`tests/e2e/`)

**Purpose:** Test complete user workflows from start to finish

**Files:**
- `test_e2e_complete_flow.py` - Complete user flow (register → login → chat → summary)

**Characteristics:**
- ⚠️ Slowest (5-30 seconds per test)
- ⚠️ Requires all services running (PostgreSQL, backend, WebSocket)
- ⚠️ Requires external API keys (Mistral AI)
- ✅ Test real user scenarios
- ✅ Test complete workflows
- ✅ Validate system behavior

**Run:**
```bash
docker-compose up -d
export MISTRAL_API_KEY=your-key
pytest tests/e2e/ -v
pytest -m e2e -v
```

## Test Markers

All tests are marked with pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - E2E tests
- `@pytest.mark.requires_services` - Requires Docker services
- `@pytest.mark.requires_api` - Requires external API keys
- `@pytest.mark.slow` - Slow-running tests

## Test Coverage

**Current Coverage Goals:**
- Unit Tests: 80%+ coverage of business logic
- Integration Tests: 60%+ coverage of API endpoints
- E2E Tests: 40%+ coverage of critical workflows

**View Coverage:**
```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

## Security

**Test Credentials:**
- Test passwords in `fixtures.py` are **ONLY for test databases**
- Never used in production
- Only valid in test environment
- Documented as test-only

**API Keys:**
- Never hardcode API keys in tests
- Use environment variables from `.env` file
- Use `app.config.settings` to access configuration

## Best Practices

1. ✅ Write tests first (TDD)
2. ✅ Use descriptive test names
3. ✅ Test both success and error cases
4. ✅ Keep tests simple and focused
5. ✅ Use fixtures for shared setup
6. ✅ Mock external dependencies in unit tests
7. ✅ Use test constants from `fixtures.py`
8. ✅ Clean up after tests
9. ✅ Run tests before committing
10. ✅ Aim for 80%+ code coverage

---

**Last Updated:** 2025-01-27
**Test Organization:** Unit / Integration / E2E
**Coverage Goal:** 80%+ for unit tests
