"""
Integration Tests
Test backend HTTP endpoints running in Docker container

These are integration tests that test multiple components working together.
May require Docker services (PostgreSQL, backend) to be running.
"""

import time

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

BASE_URL = "http://localhost:8000"


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self):
        """Test health check returns correct status"""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sumii-mobile-api"
        assert "version" in data


class TestUserRegistration:
    """Test user registration endpoint"""

    def test_register_new_user(self):
        """Test successful user registration"""
        unique_email = f"test-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["email"] == unique_email
        assert "password" not in data
        assert "hashed_password" not in data

    def test_register_duplicate_email(self):
        """Test registration with existing email returns error"""
        email = "duplicate@sumii.de"
        # Register first user
        requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": email, "password": "Password123!"},
        )

        # Try to register with same email
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": email, "password": "DifferentPass456!"},
        )
        assert response.status_code == 400
        # fastapi-users error message format may differ
        assert (
            "REGISTER_USER_ALREADY_EXISTS" in response.json()["detail"]
            or "already" in response.json()["detail"].lower()
        )

    def test_register_invalid_email(self):
        """Test registration with invalid email format"""
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": "not-an-email", "password": "Password123!"},
        )
        assert response.status_code == 422  # Validation error


class TestUserLogin:
    """Test user login endpoint"""

    def test_login_success(self):
        """Test successful login returns JWT token"""
        email = "logintest@sumii.de"
        password = "Password123!"

        # Register user first
        requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": email, "password": password},
        )

        # Login (fastapi-users uses form data, not JSON)
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": email, "password": password},  # Form data, not JSON
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 50  # JWT tokens are long

    def test_login_wrong_password(self):
        """Test login with wrong password returns 401"""
        email = "wrongpass@sumii.de"

        # Register user first
        requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": email, "password": "CorrectPassword123!"},
        )

        # Login with wrong password (fastapi-users uses form data)
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": email, "password": "WrongPassword456!"},
        )
        assert response.status_code == 400  # fastapi-users returns 400, not 401
        assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"

    def test_login_nonexistent_user(self):
        """Test login with non-existent email returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": "nonexistent@sumii.de", "password": "Password123!"},
        )
        assert response.status_code == 400  # fastapi-users returns 400, not 401
        assert response.json()["detail"] == "LOGIN_BAD_CREDENTIALS"

    def test_login_invalid_email_format(self):
        """Test login with invalid email format"""
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login", data={"username": "not-an-email", "password": "Pass123!"}
        )
        # fastapi-users may allow it through to authentication check
        assert response.status_code in [400, 422]  # Either validation error or bad credentials
