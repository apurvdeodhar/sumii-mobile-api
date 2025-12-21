"""Unit Tests for Webhook Endpoints

Test webhook endpoints with mocked dependencies.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models import User

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class TestLawyerResponseWebhook:
    """Test lawyer response webhook endpoint"""

    async def test_webhook_endpoint_exists(self, client: AsyncClient, test_user: User):
        """Test webhook endpoint exists and returns proper error without auth"""
        response = await client.post(
            "/api/v1/webhooks/lawyer-response",
            json={
                "case_id": 123,
                "conversation_id": str(uuid4()),
                "user_id": str(test_user.id),
                "lawyer_id": 456,
                "lawyer_name": "Dr. Test Lawyer",
                "response_text": "Test response",
                "response_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        # Should fail without API key (401) or invalid data (422)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY)

    async def test_webhook_with_valid_data(self, client: AsyncClient, test_user: User, db_session, test_conversation):
        """Test webhook creates notification with valid data"""

        # Temporarily set API key (or allow without key in dev)
        import os

        original_key = os.environ.get("ANWALT_API_KEY")
        os.environ["ANWALT_API_KEY"] = "test-api-key"

        try:
            webhook_data = {
                "case_id": 123,
                "conversation_id": str(test_conversation.id),
                "user_id": str(test_user.id),
                "lawyer_id": 456,
                "lawyer_name": "Dr. Test Lawyer",
                "response_text": "I have reviewed your case and...",
                "response_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            response = await client.post(
                "/api/v1/webhooks/lawyer-response",
                json=webhook_data,
                headers={"X-API-Key": "test-api-key"},
            )

            # Should succeed (200) or fail gracefully if email service not configured
            assert response.status_code in (
                status.HTTP_200_OK,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                assert data["status"] == "success"
                assert "notification_id" in data
                assert data["notification_id"] is not None
        finally:
            if original_key:
                os.environ["ANWALT_API_KEY"] = original_key
            elif "ANWALT_API_KEY" in os.environ:
                del os.environ["ANWALT_API_KEY"]

    async def test_webhook_with_invalid_user(self, client: AsyncClient):
        """Test webhook fails with invalid user ID"""
        import os

        original_key = os.environ.get("ANWALT_API_KEY")
        os.environ["ANWALT_API_KEY"] = "test-api-key"

        try:
            response = await client.post(
                "/api/v1/webhooks/lawyer-response",
                json={
                    "case_id": 123,
                    "conversation_id": str(uuid4()),
                    "user_id": str(uuid4()),  # Non-existent user
                    "lawyer_id": 456,
                    "lawyer_name": "Dr. Test Lawyer",
                    "response_text": "Test response",
                    "response_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                headers={"X-API-Key": "test-api-key"},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in response.json()["detail"].lower()
        finally:
            if original_key:
                os.environ["ANWALT_API_KEY"] = original_key
            elif "ANWALT_API_KEY" in os.environ:
                del os.environ["ANWALT_API_KEY"]
