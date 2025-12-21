"""E2E Test: Webhook → Notification → SSE Integration

Tests the complete flow:
1. Webhook receives lawyer response from sumii-anwalt
2. Notification is created in database
3. SSE endpoint streams the notification to mobile app

This validates the integration between webhook, notification, and SSE endpoints.
"""

import json
import time
from datetime import datetime, timezone

import pytest
import requests

pytestmark = [pytest.mark.e2e, pytest.mark.requires_services, pytest.mark.requires_api]

BASE_URL = "http://localhost:8000"


class TestWebhookNotificationSSEIntegration:
    """E2E tests for webhook → notification → SSE flow"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user, conversation, and authentication for each test"""
        # Register user
        unique_email = f"e2e-webhook-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        if response.status_code == 201:
            self.user_id = response.json()["id"]
        elif response.status_code == 400:
            # User exists, try login
            pass
        else:
            raise Exception(f"Failed to register: {response.status_code} - {response.text}")

        # Login to get token (fastapi-users uses form data)
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        self.token = response.json()["access_token"]
        self.user_email = unique_email
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "E2E Webhook Test Conversation"},
            timeout=10,
        )
        assert response.status_code == 201, f"Failed to create conversation: {response.status_code} - {response.text}"
        self.conversation_id = response.json()["id"]

    def test_webhook_creates_notification_streamed_via_sse(self):
        """Test complete flow: webhook → notification → SSE"""
        # Step 1: Call webhook endpoint (simulating sumii-anwalt)
        webhook_data = {
            "case_id": 12345,
            "conversation_id": str(self.conversation_id),
            "user_id": str(self.user_id),
            "lawyer_id": 456,
            "lawyer_name": "Dr. E2E Test Lawyer",
            "response_text": "I have reviewed your case and here is my professional response.",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        webhook_response = requests.post(
            f"{BASE_URL}/api/v1/webhooks/lawyer-response",
            json=webhook_data,
            headers={"X-API-Key": "test-key"},  # API key auth disabled in dev
            timeout=10,
        )

        assert (
            webhook_response.status_code == 200
        ), f"Webhook failed: {webhook_response.status_code} - {webhook_response.text}"
        webhook_result = webhook_response.json()
        assert webhook_result["status"] == "success"
        assert "notification_id" in webhook_result

        # Step 2: Subscribe to SSE events
        sse_response = requests.get(
            f"{BASE_URL}/api/v1/events/subscribe",
            params={"token": self.token},
            stream=True,
            timeout=5,
        )

        assert sse_response.status_code == 200
        assert sse_response.headers.get("Content-Type", "").startswith("text/event-stream")

        # Step 3: Read SSE events and look for our notification
        events_received = []
        try:
            for line in sse_response.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    event_data = json.loads(line[6:])  # Remove "data: " prefix
                    events_received.append(event_data)

                    # Check if we got our lawyer response notification
                    if event_data.get("type") == "lawyer_response":
                        assert event_data["title"] == "Anwalt hat geantwortet"
                        assert "lawyer_name" in event_data.get("data", {})
                        assert event_data["data"]["lawyer_name"] == webhook_data["lawyer_name"]
                        assert event_data["data"]["case_id"] == webhook_data["case_id"]
                        # Found our notification, break
                        break

                # Timeout after reading some events (notification should arrive quickly)
                if len(events_received) >= 20:
                    break
        finally:
            sse_response.close()

        # Verify we received the notification
        assert len(events_received) > 0, "No events received via SSE"
        lawyer_response_events = [e for e in events_received if e.get("type") == "lawyer_response"]
        assert len(lawyer_response_events) > 0, f"Lawyer response notification not found in events: {events_received}"
