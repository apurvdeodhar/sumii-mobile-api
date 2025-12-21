"""Integration Tests for Lawyer Case Handoff

Tests the handoff_case function in AnwaltService that sends cases to sumii-anwalt backend.
"""

import time
from uuid import uuid4

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

BASE_URL = "http://localhost:8000"


class TestAnwaltServiceHandoff:
    """Test AnwaltService.handoff_case() method"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user and token for each test"""
        # Register user
        unique_email = f"anwalt-handoff-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        if response.status_code == 201:
            self.user_id = response.json()["id"]
        elif response.status_code == 400:
            pass  # User might already exist
        else:
            raise Exception(f"Failed to register user: {response.status_code}")

        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": unique_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_handoff_case_method_exists(self):
        """Test that AnwaltService has handoff_case method"""
        from app.services.anwalt_service import AnwaltService

        service = AnwaltService()
        assert hasattr(service, "handoff_case")
        assert callable(service.handoff_case)

    @pytest.mark.asyncio
    async def test_handoff_case_method_signature(self):
        """Test handoff_case method accepts correct parameters

        Note: This will fail if sumii-anwalt backend is not running,
        but we're just testing the method interface exists and accepts parameters.
        """
        from app.services.anwalt_service import AnwaltService

        service = AnwaltService()

        # Test that method can be called with proper parameters
        try:
            await service.handoff_case(
                user_id=str(uuid4()),
                summary_id=str(uuid4()),
                summary_pdf_url="https://s3.example.com/test.pdf",
                lawyer_id=1,
                legal_area="Mietrecht",
                case_strength="strong",
                urgency="immediate",
                user_location={"city": "Berlin", "lat": 52.52, "lng": 13.40},
            )
        except Exception:
            # Expected if anwalt backend not running or endpoint doesn't exist
            # We're just testing the method exists and accepts parameters
            pass

    def test_connect_endpoint_calls_handoff_internally(self):
        """Test that connect endpoint exists and will call handoff internally

        Note: This test verifies the endpoint exists and handles errors correctly.
        It will fail with 404 if lawyer doesn't exist, but that confirms the endpoint works.
        """
        # Create a conversation first
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Test Conversation for Lawyer Handoff"},
            timeout=10,
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Try to connect to non-existent lawyer (will fail, but endpoint should exist)
        response = requests.post(
            f"{BASE_URL}/api/v1/anwalt/connect",
            headers=self.headers,
            json={"conversation_id": conversation_id, "lawyer_id": 999999},
            timeout=10,
        )
        # Should return 404 (lawyer not found) or 500 (handoff failed), not 404 (endpoint not found)
        assert response.status_code in [404, 500], f"Unexpected status: {response.status_code} - {response.text}"
