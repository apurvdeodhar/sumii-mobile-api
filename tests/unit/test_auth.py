"""
Authentication Tests (Unit Tests)
Test user registration, login, and JWT token validation

These are unit tests that test individual components in isolation.
All external dependencies are mocked.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.unit


class TestHealthCheck:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns correct status"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sumii-mobile-api"
        assert "version" in data


class TestUserRegistration:
    """Test user registration endpoint"""

    @pytest.mark.asyncio
    async def test_register_new_user(self, client: AsyncClient):
        """Test successful user registration"""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@sumii.de", "password": "SecurePassword123!"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@sumii.de"
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        """Test registration with existing email returns error"""
        # Register first user
        await client.post(
            "/api/v1/auth/register",
            json={"email": "duplicate@sumii.de", "password": "Password123!"},
        )

        # Try to register with same email
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "duplicate@sumii.de", "password": "DifferentPass456!"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Email already registered"

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email format"""
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "Password123!"},
        )
        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Test user login endpoint"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient):
        """Test successful login returns JWT token"""
        # Register user first
        await client.post(
            "/api/v1/auth/register",
            json={"email": "login@sumii.de", "password": "Password123!"},
        )

        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@sumii.de", "password": "Password123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50  # JWT tokens are long

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient):
        """Test login with wrong password returns 401"""
        # Register user first
        await client.post(
            "/api/v1/auth/register",
            json={"email": "wrongpass@sumii.de", "password": "CorrectPassword123!"},
        )

        # Login with wrong password
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrongpass@sumii.de", "password": "WrongPassword456!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent email returns 401"""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@sumii.de", "password": "Password123!"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client: AsyncClient):
        """Test login with invalid email format"""
        response = await client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "Pass123!"})
        assert response.status_code == 422  # Validation error
