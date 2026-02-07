# Sumii Mobile API

FastAPI backend for Sumii mobile app - an intelligent, empathetic lawyer assistant that interviews users, gathers facts, creates lawyer-ready summaries, and connects users with the right lawyers.

**Purpose**: Backend API for user-facing mobile app (iOS + Android)

**Note**: This is separate from the lawyer-facing backend (`sumii-anwalt-api`)

## 🚀 Quick Start

```bash
# 1. Navigate to backend
cd /Users/apurva/Work/sumii/sumii-v2/sumii-mobile-api

# 2. Read development guide
open CLAUDE.md

# 3. Follow Hour 0-8 setup checklist
```

## 📚 Documentation

- **CLAUDE.md** - Comprehensive development guide (start here!)
- **tests/README.md** - **Testing & TDD Guide** (required reading!)
- **docs/CURRENT_STATE.md** - Current project status and features
- **docs/MOBILE_APP_INTEGRATION.md** - Mobile app integration guide
- **docs/PROD_DEPLOYMENT.md** - Production deployment to AWS ECS
- **docs/typescript-types.ts** - TypeScript types for mobile app (auto-generated)
- **infrastructure/** - Terraform configuration for AWS
- **API Docs** - https://api.sumii.de/docs (Swagger UI)

## 🔧 Tech Stack

- Python 3.13
- FastAPI
- PostgreSQL 16
- Mistral AI
- AWS (S3, SES, SNS, SQS)
- Docker + Docker Compose

## 📁 Structure

```
sumii-mobile-api/
├── app/                    # Application code
│   ├── main.py            # FastAPI entry point
│   ├── api/v1/            # API endpoints (versioned)
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/           # Pydantic validation schemas
│   ├── services/          # Business logic services
│   └── utils/             # Utilities (security, helpers)
├── alembic/               # Database migrations
│   └── versions/          # Migration files
├── docs/                  # Documentation
│   ├── MOBILE_APP_INTEGRATION.md  # Mobile integration guide
│   ├── PROD_DEPLOYMENT.md         # Production deployment
│   └── typescript-types.ts        # TypeScript types (auto-gen)
├── infrastructure/        # Terraform for AWS
│   ├── ecs.tf            # ECS Fargate task & service
│   ├── rds.tf            # RDS PostgreSQL database
│   ├── s3.tf             # S3 buckets (PDFs, documents)
│   ├── sns_sqs.tf        # SNS/SQS for notifications
│   └── outputs.tf        # Centralized Terraform outputs
├── scripts/               # Utility scripts
│   ├── build-and-push.sh # Docker build & ECR push
│   └── pydantic_to_typescript.py # TypeScript type generator
├── Dockerfile             # Multi-stage Docker build
├── start.sh               # Container startup (migrations + uvicorn)
├── docker-compose.yml     # PostgreSQL + Backend services
├── pyproject.toml         # Dependencies (uv package manager)
├── alembic.ini            # Alembic configuration
├── .env                   # Secrets (NEVER COMMIT!)
├── .pre-commit-config.yaml # 18 automated code quality checks
├── .tflint.hcl            # TFLint configuration
├── .trivyignore           # Trivy security scan exceptions
├── CLAUDE.md              # Development guide
└── README.md              # This file
```

## ⚙️ Local Development

```bash
# 1. Navigate to project directory
cd /Users/apurva/Work/sumii/sumii-v2/sumii-mobile-api

# 2. Create .env file with secrets
cat > .env << 'EOF'
MISTRAL_API_KEY=your-mistral-api-key-here
SECRET_KEY=your-jwt-secret-key-generate-with-openssl-rand-base64-32
# Optional: Mistral API read timeout in seconds (default: 120s)
# Increase if you see SSL ReadError or stream timeouts during long AI responses
MISTRAL_READ_TIMEOUT=120.0
EOF

# 3. Start all services (PostgreSQL + Backend)
docker-compose up -d

# 4. View logs
docker-compose logs -f backend

# 5. Access API
open http://localhost:8000/docs    # Swagger UI
curl http://localhost:8000/health   # Health check

# 6. Stop services
docker-compose down
```

### Hot Reload

Code changes in `app/` are automatically hot-reloaded in Docker container (< 1 second)!

### Run Tests

**We follow Test-Driven Development (TDD) - see [Testing Guide](tests/README.md) for details.**

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Run all tests (unit + integration + e2e)
pytest -v

# 3. Run specific test categories
pytest -m unit -v              # Unit tests only (fast, no services needed)
pytest -m integration -v       # Integration tests (requires Docker services)
pytest -m e2e -v                # E2E tests (requires all services + API keys)

# 4. Run with coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html

# 5. Run tests inside container
docker-compose exec backend pytest
```

**Test Structure:**

- `tests/unit/` - Fast, isolated unit tests (mocked dependencies)
- `tests/integration/` - Integration tests (multiple components)
- `tests/e2e/` - End-to-end tests (complete workflows)

**See [tests/README.md](tests/README.md) for comprehensive testing guide.**

## 🧪 Testing & TDD

**We strictly follow Test-Driven Development (TDD).**

### TDD Workflow

1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to make it pass
3. **REFACTOR**: Improve code quality
4. **REPEAT**

### Test Requirements

- ✅ **All new features must have tests** (unit, integration, or e2e)
- ✅ **Tests must pass before committing** (`pytest -v`)
- ✅ **Aim for 80%+ code coverage** for new code
- ✅ **No hardcoded secrets** in tests (use environment variables)
- ✅ **Tests must be properly categorized** (unit/integration/e2e)

### Quick Test Commands

```bash
# Run all tests
pytest -v

# Run by category
pytest -m unit -v              # Unit tests (fast, isolated)
pytest -m integration -v       # Integration tests (requires services)
pytest -m e2e -v                # E2E tests (requires all services)

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_auth.py -v
```

**📚 Full Testing Guide:** See [tests/README.md](tests/README.md) for:

- TDD guidelines and workflow
- Test structure and categories
- Writing tests best practices
- Coverage requirements
- Troubleshooting

## 📝 Logging Configuration

**Simple, centralized logging using Python's standard library** - no external dependencies.

### Features

- ✅ **Environment variable configuration** - All settings via `.env` file
- ✅ **Standard Python logging** - Uses `logging.basicConfig()` (simple, maintainable)
- ✅ **Noise suppression** - SQLAlchemy and Uvicorn logs configured appropriately
- ✅ **Zero dependencies** - Only uses Python standard library

### Configuration

**Environment Variables** (`.env` file):

```bash
# Global log level
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Usage

**In your code** (no changes needed!):

```python
import logging
logger = logging.getLogger(__name__)

logger.info("This works!")
logger.debug("Debug message")
logger.error("Error message")
```

### Log Format

```
2025-12-13 23:38:08 | app.services.summary_service | INFO     | Summary generated successfully
```

**Format**: `%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s`

### What's Suppressed

- ✅ **SQLAlchemy engine logs** - CRITICAL only (suppressed)
- ✅ **Uvicorn startup/shutdown** - WARNING and above (reduces noise)
- ✅ **Uvicorn access logs** - INFO level (HTTP requests visible)
- ✅ **AWS SDK logs** - WARNING and above

### Implementation

- **File**: `app/utils/logging_config.py` (76 lines, simple and maintainable)
- **Initialization**: Called once in `app/main.py` at startup
- **Configuration**: Via Pydantic Settings (`app/config.py`)

**See `docs/LOGGING_FINAL.md` for detailed documentation.**

## 🧪 Current Features

### Core Features ✅

- ✅ **User Authentication** (fastapi-users)

  - User registration & login
  - Email verification (AWS SES)
  - Password reset (AWS SES)
  - Google OAuth support
  - JWT tokens (60-minute expiry)

- ✅ **Conversation Management**

  - Create, read, update, delete conversations
  - Message storage and retrieval
  - Conversation state tracking (5W facts, analysis, summaries)

- ✅ **AI Chat Integration** (Mistral AI)

  - Real-time WebSocket chat
  - 4 Mistral Agents (Router, Intake, Reasoning, Summary)
  - Dynamic agent orchestration
  - Document library integration (BGB sections, case examples, templates)
  - **Custom httpx timeout configuration** (120s read timeout for streaming)

### Mistral Client Configuration

The Mistral SDK uses `httpx` internally for HTTP/HTTPS requests. We configure custom timeouts to prevent SSL ReadErrors and stream timeouts during long AI responses (especially during Magistral's "thinking" phase).

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Local/Production App                                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  app/services/mistral_client.py                            ││
│  │  ├─ get_mistral_client() → Mistral(client=httpx.Client())  ││
│  │  └─ get_mistral_async_client() → Mistral(async_client=...) ││
│  └────────────────────────────────────┬────────────────────────┘│
│                                       │ HTTPS (TLS 1.3)         │
└───────────────────────────────────────┼─────────────────────────┘
                                        ▼
                             ┌──────────────────────┐
                             │  api.mistral.ai      │
                             │  (Mistral Cloud API) │
                             └──────────────────────┘
```

**Timeout Settings** (`MISTRAL_READ_TIMEOUT` env var, default 120s):
- `connect=10s` - Max time to establish connection
- `read=120s` - Max time to wait for streaming response data (**critical!**)
- `write=30s` - Max time to send request data
- `pool=10s` - Max time to wait for connection from pool

**Reference:** [client-python#70](https://github.com/mistralai/client-python/issues/70)

- ✅ **Document Management**

  - PDF upload to S3
  - OCR processing (Mistral Vision API)
  - Document retrieval and deletion

- ✅ **Legal Summary Generation**

  - AI-powered summary generation
  - PDF export (WeasyPrint)
  - S3 storage with pre-signed URLs

- ✅ **Lawyer Integration**

  - Lawyer search by location and specialization
  - Case handoff to sumii-anwalt backend
  - Lawyer connection tracking

- ✅ **Notifications**

  - Server-Sent Events (SSE) for real-time notifications
  - Email notifications (AWS SES)
  - Webhook endpoint for lawyer responses

- ✅ **Status & Health Checks**
  - API health check
  - Agent status monitoring
  - Conversation progress tracking

### Infrastructure ✅

- ✅ Database migrations (Alembic)
- ✅ Comprehensive test suite (96% pass rate: 104/108 tests)
- ✅ TDD workflow established
- ✅ Pre-commit hooks (14 checks, all passing)
- ✅ Docker containerization with hot reload
- ✅ API documentation (Swagger/ReDoc at `/docs`)

**See `CLAUDE.md` for comprehensive development guide!**

## 🚀 Deployment

### Production (AWS ECS Fargate)

**Live API**: https://api.sumii.de

| Resource | Details |
|----------|--------|
| ECS Cluster | `sumii-global-cluster` |
| Service | `sumii-mobile-api` |
| RDS | `sumii-mobile-api-db-v2` (PostgreSQL 14) |
| Region | `eu-central-1` |

**Deploy:**
```bash
# Build and push Docker image
./scripts/build-and-push.sh

# Apply infrastructure
cd infrastructure && terraform apply
```

See `docs/PROD_DEPLOYMENT.md` for full deployment guide.

### Local Development

```bash
docker-compose up -d           # Start PostgreSQL + Backend
curl http://localhost:8000/health  # Verify
```

## 🔒 Security

- ✅ JWT tokens (60-minute expiry)
- ✅ bcrypt password hashing (12 rounds)
- ✅ Environment secrets in `.env` (gitignored)
- ✅ Pre-commit secret detection
- ✅ SQL injection prevention (SQLAlchemy ORM)
- ✅ Input validation (Pydantic schemas)

**Production**: Use AWS Secrets Manager

## 📊 Current Status (Updated: 2026-02-07)

**Project**: Production-ready MVP ✅
**Live API**: https://api.sumii.de/health
**Container**: `sumii-mobile-api` on ECS Fargate

### Quality Checks

- ✅ **Pre-commit**: 18/18 hooks passing (Ruff, Mypy, TFLint, Checkov, Trivy)
- ✅ **Tests**: 96% pass rate (104/108 tests)
- ✅ **Security**: SQS/SNS encryption, S3 public access blocks
- ✅ **TDD**: Strictly enforced

---

**Status**: ✅ **Production-deployed** - API running at api.sumii.de

For detailed development guide, see `CLAUDE.md`
