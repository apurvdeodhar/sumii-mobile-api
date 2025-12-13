"""Conversation CRUD Integration Tests

Test conversation endpoints against running backend.
These tests require Docker services to be running.
"""

import time
from uuid import uuid4

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

BASE_URL = "http://localhost:8000"


class TestConversationCRUD:
    """Test conversation CRUD operations"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user and token for each test"""
        # Register user
        unique_email = f"conv-test-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 201
        self.user_id = response.json()["id"]

        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_create_conversation(self):
        """Test creating a new conversation"""
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Test Conversation"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["title"] == "Test Conversation"
        assert data["status"] == "active"
        assert data["current_agent"] == "router"
        assert data["user_id"] == self.user_id

    def test_create_conversation_auto_title(self):
        """Test creating conversation without title (auto-generated)"""
        response = requests.post(f"{BASE_URL}/api/v1/conversations", headers=self.headers, json={})
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "title" in data
        assert data["title"].startswith("Conversation ")

    def test_list_conversations(self):
        """Test listing all user conversations"""
        # Create a conversation first
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Test Conversation 1"},
        )
        assert response.status_code == 201
        conv1_id = response.json()["id"]

        # Create another conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Test Conversation 2"},
        )
        assert response.status_code == 201
        conv2_id = response.json()["id"]

        # List conversations
        response = requests.get(f"{BASE_URL}/api/v1/conversations", headers=self.headers)
        assert response.status_code == 200
        conversations = response.json()
        assert isinstance(conversations, list)
        assert len(conversations) >= 2

        # Verify both conversations are in the list
        conv_ids = [c["id"] for c in conversations]
        assert conv1_id in conv_ids
        assert conv2_id in conv_ids

        # Verify conversations are ordered by creation date (newest first)
        assert conversations[0]["id"] == conv2_id  # Most recent first

    def test_get_conversation_with_messages(self):
        """Test getting a conversation with all messages"""
        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Test Conversation"},
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Get conversation
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == conversation_id
        assert "messages" in data
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) == 0  # No messages yet

    def test_get_conversation_not_found(self):
        """Test getting non-existent conversation returns 404"""
        fake_id = str(uuid4())
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{fake_id}",
            headers=self.headers,
        )
        assert response.status_code == 404

    def test_get_conversation_unauthorized(self):
        """Test getting another user's conversation returns 403"""
        # Create another user
        other_email = f"other-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 201

        # Other user creates conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 200
        other_token = response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=other_headers,
            json={"title": "Other User's Conversation"},
        )
        assert response.status_code == 201
        other_conv_id = response.json()["id"]

        # Try to access other user's conversation
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{other_conv_id}",
            headers=self.headers,  # Using original user's token
        )
        assert response.status_code == 403

    def test_update_conversation(self):
        """Test updating conversation metadata"""
        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Original Title"},
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Update conversation
        response = requests.patch(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            json={
                "title": "Updated Title",
                "legal_area": "Mietrecht",
                "case_strength": "strong",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["legal_area"] == "Mietrecht"
        assert data["case_strength"] == "strong"

    def test_update_conversation_not_found(self):
        """Test updating non-existent conversation returns 404"""
        fake_id = str(uuid4())
        response = requests.patch(
            f"{BASE_URL}/api/v1/conversations/{fake_id}",
            headers=self.headers,
            json={"title": "Updated Title"},
        )
        assert response.status_code == 404

    def test_update_conversation_unauthorized(self):
        """Test updating another user's conversation returns 403"""
        # Create another user and conversation
        other_email = f"other-update-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        other_token = response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=other_headers,
            json={"title": "Other User's Conversation"},
        )
        other_conv_id = response.json()["id"]

        # Try to update other user's conversation
        response = requests.patch(
            f"{BASE_URL}/api/v1/conversations/{other_conv_id}",
            headers=self.headers,
            json={"title": "Hacked Title"},
        )
        assert response.status_code == 403

    def test_delete_conversation(self):
        """Test deleting a conversation"""
        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "To Be Deleted"},
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Delete conversation
        response = requests.delete(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
        )
        assert response.status_code == 204

        # Verify conversation is gone
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
        )
        assert response.status_code == 404

    def test_delete_conversation_not_found(self):
        """Test deleting non-existent conversation returns 404"""
        fake_id = str(uuid4())
        response = requests.delete(
            f"{BASE_URL}/api/v1/conversations/{fake_id}",
            headers=self.headers,
        )
        assert response.status_code == 404

    def test_delete_conversation_unauthorized(self):
        """Test deleting another user's conversation returns 403"""
        # Create another user and conversation
        other_email = f"other-delete-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": other_email, "password": "SecurePassword123!"},
        )
        other_token = response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=other_headers,
            json={"title": "Other User's Conversation"},
        )
        other_conv_id = response.json()["id"]

        # Try to delete other user's conversation
        response = requests.delete(
            f"{BASE_URL}/api/v1/conversations/{other_conv_id}",
            headers=self.headers,
        )
        assert response.status_code == 403
