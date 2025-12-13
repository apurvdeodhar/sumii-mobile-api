"""Status Endpoint Integration Tests

Test status and health check endpoints against running backend.
These tests require Docker services to be running.
"""

import time
from uuid import uuid4

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

BASE_URL = "http://localhost:8000"


class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self):
        """Test health check returns correct status"""
        response = requests.get(f"{BASE_URL}/api/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "sumii-mobile-api"
        assert "version" in data
        assert "timestamp" in data
        assert "environment" in data


class TestAgentStatus:
    """Test agent status endpoint"""

    def test_agent_status(self):
        """Test agent status returns all agents"""
        response = requests.get(f"{BASE_URL}/api/v1/status/agents")
        assert response.status_code == 200
        data = response.json()
        assert "total_agents" in data
        assert "ready_agents" in data
        assert "all_ready" in data
        assert "agents" in data
        assert "mistral_api_configured" in data
        assert "timestamp" in data

        # Verify agent structure
        agents = data["agents"]
        assert "router" in agents
        assert "intake" in agents
        assert "reasoning" in agents
        assert "summary" in agents

        # Verify each agent has status
        for agent_name, agent_data in agents.items():
            assert "status" in agent_data
            assert "agent_id" in agent_data

        # Verify counts match
        assert data["total_agents"] == 4
        assert data["ready_agents"] <= data["total_agents"]


class TestConversationProgress:
    """Test conversation progress endpoint"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user, token, and conversation for each test"""
        # Register user
        unique_email = f"status-test-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 201

        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": unique_email, "password": "SecurePassword123!"},
        )
        assert response.status_code == 200
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create conversation
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Status Test Conversation"},
        )
        assert response.status_code == 201
        self.conversation_id = response.json()["id"]

    def test_conversation_progress(self):
        """Test getting conversation progress"""
        response = requests.get(
            f"{BASE_URL}/api/v1/status/conversations/{self.conversation_id}",
            headers=self.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == self.conversation_id
        assert "status" in data
        assert "current_agent" in data
        assert "workflow_progress" in data
        assert "next_step" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "timestamp" in data

        # Verify workflow progress structure
        workflow = data["workflow_progress"]
        assert "facts_collection" in workflow
        assert "legal_analysis" in workflow
        assert "summary_generation" in workflow

        # Verify facts collection structure
        facts_collection = workflow["facts_collection"]
        assert "status" in facts_collection
        assert "completeness" in facts_collection
        completeness = facts_collection["completeness"]
        assert "who" in completeness
        assert "what" in completeness
        assert "when" in completeness
        assert "where" in completeness
        assert "why" in completeness

    def test_conversation_progress_not_found(self):
        """Test getting progress for non-existent conversation returns 404"""
        fake_id = str(uuid4())
        response = requests.get(
            f"{BASE_URL}/api/v1/status/conversations/{fake_id}",
            headers=self.headers,
        )
        assert response.status_code == 404

    def test_conversation_progress_unauthorized(self):
        """Test getting progress for another user's conversation returns 403"""
        # Create another user and conversation
        other_email = f"other-status-{int(time.time() * 1000)}@sumii.de"
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

        # Try to get progress for other user's conversation
        response = requests.get(
            f"{BASE_URL}/api/v1/status/conversations/{other_conv_id}",
            headers=self.headers,
        )
        assert response.status_code == 403
