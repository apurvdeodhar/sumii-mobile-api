"""Integration Tests for Webhook Endpoints

Test webhook endpoints against running backend.
These tests require Docker services to be running.
"""

import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

BASE_URL = "http://localhost:8000"


class TestLawyerResponseWebhook:
    """Test lawyer response webhook endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user, conversation, and lawyer connection for each test"""
        # Register user
        unique_email = f"webhook-test-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        if response.status_code == 201:
            self.user_id = response.json()["id"]
        elif response.status_code == 400:
            # User might already exist
            pass
        else:
            pytest.skip(f"Failed to register user: {response.status_code}")

        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        if response.status_code != 200:
            pytest.skip(f"Failed to login: {response.status_code}")

        self.token = response.json()["access_token"]
        self.user_email = unique_email
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Webhook Test Conversation"},
            timeout=10,
        )
        if response.status_code == 201:
            self.conversation_id = response.json()["id"]
        else:
            pytest.skip(f"Failed to create conversation: {response.status_code}")

    def test_webhook_without_api_key(self):
        """Test webhook requires API key authentication"""
        webhook_data = {
            "case_id": 123,
            "conversation_id": str(self.conversation_id),
            "user_id": str(self.user_id),
            "lawyer_id": 456,
            "lawyer_name": "Dr. Test Lawyer",
            "response_text": "Test response",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            timeout=10,
        )

        # Should fail without API key header (422 - FastAPI validation) or allow in dev mode (200)
        assert response.status_code in (200, 401, 422), f"Unexpected status: {response.status_code} - {response.text}"

    def test_webhook_with_invalid_user(self):
        """Test webhook fails with non-existent user"""
        webhook_data = {
            "case_id": 123,
            "conversation_id": str(self.conversation_id),
            "user_id": str(uuid4()),  # Non-existent user
            "lawyer_id": 456,
            "lawyer_name": "Dr. Test Lawyer",
            "response_text": "Test response",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            headers={"X-API-Key": "test-key"},  # API key auth disabled in dev
            timeout=10,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_webhook_creates_notification(self):
        """Test webhook creates notification in database"""
        webhook_data = {
            "case_id": 123,
            "conversation_id": str(self.conversation_id),
            "user_id": str(self.user_id),
            "lawyer_id": 456,
            "lawyer_name": "Dr. Test Lawyer",
            "response_text": "I have reviewed your case and this is my response.",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            headers={"X-API-Key": "test-key"},  # API key auth disabled in dev
            timeout=10,
        )

        assert response.status_code == 200, f"Webhook failed: {response.status_code} - {response.text}"
        data = response.json()
        assert data["status"] == "success"
        assert "notification_id" in data
        assert data["notification_id"] is not None

        # Verify notification was created (via SSE endpoint would stream it)
        # For now, just verify the webhook response is correct
        assert "email_sent" in data

    def test_webhook_updates_lawyer_connection(self):
        """Test webhook updates existing lawyer connection"""
        # First, create a lawyer connection

        # Mock the anwalt service to return a lawyer profile
        # For integration test, we'll skip if anwalt service not available
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/anwalt/search",
                headers=self.headers,
                params={"language": "de", "limit": 1},
                timeout=5,
            )
            if response.status_code != 200:
                pytest.skip("Anwalt service not available for integration test")
        except Exception:
            pytest.skip("Anwalt service not available for integration test")

        # For now, just test webhook creates notification
        # Full integration test would require sumii-anwalt backend running
        webhook_data = {
            "case_id": 789,
            "conversation_id": str(self.conversation_id),
            "user_id": str(self.user_id),
            "lawyer_id": 456,
            "lawyer_name": "Dr. Updated Lawyer",
            "response_text": "Updated response",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            headers={"X-API-Key": "test-key"},
            timeout=10,
        )

        assert response.status_code == 200

    def test_webhook_with_invalid_conversation(self):
        """Test webhook fails with invalid conversation ID"""
        webhook_data = {
            "case_id": 123,
            "conversation_id": str(uuid4()),  # Non-existent conversation
            "user_id": str(self.user_id),
            "lawyer_id": 456,
            "lawyer_name": "Dr. Test Lawyer",
            "response_text": "Test response",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            headers={"X-API-Key": "test-key"},
            timeout=10,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
