"""
OTP Password Reset Tests

Tests for the 6-digit OTP-based password reset flow.
Covers: request OTP, validation, full reset flow, code reuse prevention.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.unit


class TestForgotPasswordOTP:
    """Test POST /api/v1/auth/forgot-password"""

    @pytest.mark.asyncio
    async def test_returns_202_for_existing_email(self, client: AsyncClient, test_user):
        """Always returns 202 even for known emails (no email enumeration)."""
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_user.email},
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_returns_202_for_nonexistent_email(self, client: AsyncClient):
        """Returns 202 for unknown email — prevents enumeration attacks."""
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "doesnotexist@example.com"},
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_malformed_email_returns_422(self, client: AsyncClient):
        """Returns 422 for non-email input."""
        response = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 422


class TestResetPasswordOTP:
    """Test POST /api/v1/auth/reset-password"""

    @pytest.mark.asyncio
    async def test_invalid_code_returns_400(self, client: AsyncClient, test_user):
        """Returns 400 for an OTP code that was never issued."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": "000000", "password": "newpassword123"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_short_password_returns_422(self, client: AsyncClient, test_user):
        """Returns 422 for passwords shorter than 8 characters."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": "123456", "password": "short"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_numeric_code_returns_422(self, client: AsyncClient, test_user):
        """Returns 422 if the code contains non-digit characters."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": "abc123", "password": "newpassword123"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_full_otp_reset_flow(self, client: AsyncClient, test_user, db_session):
        """Full flow: request OTP → fetch from DB → reset → verify new login works."""
        from sqlalchemy import select

        from app.models.password_reset_code import PasswordResetCode

        # Request OTP
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_user.email},
        )
        assert resp.status_code == 202

        # Fetch OTP from DB (simulates reading from email)
        result = await db_session.execute(
            select(PasswordResetCode).where(
                PasswordResetCode.user_id == test_user.id,
                PasswordResetCode.used == False,  # noqa: E712
            )
        )
        code_record = result.scalar_one()
        otp = code_record.code
        assert len(otp) == 6
        assert otp.isdigit()

        # Reset password with valid OTP
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": otp, "password": "newpassword123"},
        )
        assert resp.status_code == 200

        # Verify code is marked used
        await db_session.refresh(code_record)
        assert code_record.used is True

        # Old password no longer works
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user.email, "password": "testpass123"},
        )
        assert resp.status_code == 400

        # New password works
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": test_user.email, "password": "newpassword123"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_used_code_cannot_be_reused(self, client: AsyncClient, test_user, db_session):
        """A code already used returns 400 on second attempt."""
        from sqlalchemy import select

        from app.models.password_reset_code import PasswordResetCode

        await client.post("/api/v1/auth/forgot-password", json={"email": test_user.email})

        result = await db_session.execute(
            select(PasswordResetCode).where(
                PasswordResetCode.user_id == test_user.id,
                PasswordResetCode.used == False,  # noqa: E712
            )
        )
        otp = result.scalar_one().code

        # First reset
        await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": otp, "password": "password123"},
        )

        # Second attempt with same code — must fail
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"email": test_user.email, "code": otp, "password": "anotherpassword"},
        )
        assert resp.status_code == 400
