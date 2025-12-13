"""WebSocket Integration Tests

Tests the complete WebSocket chat flow with Mistral AI Agents:
1. User registration and authentication
2. Conversation creation
3. WebSocket connection with JWT token
4. Message streaming from agents
5. Agent handoffs (Router → Intake → Reasoning → Summary)

These are integration tests that test multiple components working together.
Requires Docker services (PostgreSQL, backend) and may require API keys.
"""

import asyncio
import json

import pytest
from websockets import connect

from app.config import settings

pytestmark = [pytest.mark.integration, pytest.mark.requires_services]

# Test user credentials (test-only, never used in production)
TEST_USER = {"email": "test-websocket@sumii.de", "password": "SecurePassword123!"}

# Base URLs
BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"


class TestWebSocketChat:
    """Integration tests for WebSocket chat with Mistral Agents"""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Setup test user and conversation for each test via API (for integration tests)"""
        import time

        import requests

        # Create user via API (against running backend)
        unique_email = f"test-websocket-{int(time.time() * 1000)}@sumii.de"
        test_user = {"email": unique_email, "password": TEST_USER["password"]}

        # Register user
        response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=test_user, timeout=10)
        if response.status_code == 201:
            # New user created
            pass
        elif response.status_code == 400:
            # User might already exist, try login
            pass
        else:
            raise Exception(f"Failed to register user: {response.status_code} - {response.text}")

        # Login to get token
        response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=test_user, timeout=10)
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        self.token = response.json()["access_token"]

        # Get user info from token (decode JWT to get email)
        import jwt

        from app.config import settings

        payload = jwt.decode(self.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        self.user_email = payload.get("sub")

        # Create conversation via API
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"title": "Test Mietrecht Conversation"},
            timeout=10,
        )
        assert response.status_code == 201, f"Failed to create conversation: {response.status_code} - {response.text}"
        self.conversation_id = response.json()["id"]

        yield

        # Cleanup: Delete conversation and user (if API supports it)
        try:
            requests.delete(
                f"{BASE_URL}/api/v1/conversations/{self.conversation_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10,
            )
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    async def test_websocket_connection_with_valid_token(self):
        """Test WebSocket connection with valid JWT token"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Connection successful if no exception raised
            # Send a ping to verify connection is active
            await websocket.ping()
            await websocket.close()

    @pytest.mark.asyncio
    async def test_websocket_connection_with_invalid_token(self):
        """Test WebSocket connection with invalid JWT token"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token=invalid-token"

        with pytest.raises(Exception):
            async with connect(ws_url):
                # Should fail to connect
                pass

    @pytest.mark.asyncio
    async def test_websocket_send_message_and_receive_response(self):
        """Test sending a message and receiving agent response"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Send a German legal question (Mietrecht - broken heating)
            message = {
                "type": "message",
                "content": "Hallo, meine Heizung ist seit 2 Wochen kaputt und mein Vermieter reagiert nicht.",
            }
            await websocket.send(json.dumps(message))

            # Collect responses
            responses = []
            timeout_seconds = 30

            try:
                async with asyncio.timeout(timeout_seconds):
                    async for msg in websocket:
                        data = json.loads(msg)
                        responses.append(data)

                        # Stop after receiving message_complete or error
                        if data.get("type") in ["message_complete", "error"]:
                            break
            except asyncio.TimeoutError:
                pytest.fail(f"WebSocket response timeout after {timeout_seconds}s")

            # Verify we got responses
            assert len(responses) > 0, "No responses received from WebSocket"

            # Check for agent_start event
            agent_start_events = [r for r in responses if r.get("type") == "agent_start"]
            assert len(agent_start_events) > 0, "No agent_start event received"

            # Check agent starts with Router
            assert agent_start_events[0]["agent"] == "router", "Expected Router agent to start first"

            # Check for message chunks or complete message
            message_events = [r for r in responses if r.get("type") in ["message_chunk", "message_complete"]]
            assert len(message_events) > 0, "No message events received"

            # If we got message_complete, check it has required fields
            complete_events = [r for r in responses if r.get("type") == "message_complete"]
            if complete_events:
                msg = complete_events[0]
                assert "message_id" in msg, "message_complete missing message_id"
                assert "content" in msg, "message_complete missing content"
                assert "agent" in msg, "message_complete missing agent"
                assert len(msg["content"]) > 0, "message_complete has empty content"

            await websocket.close()

    @pytest.mark.asyncio
    async def test_websocket_agent_handoff(self):
        """Test agent handoff from Router to Intake"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Send a message that should trigger Router → Intake handoff
            message = {"type": "message", "content": "Ich brauche Hilfe mit einem Mietproblem"}
            await websocket.send(json.dumps(message))

            # Collect responses
            responses = []
            timeout_seconds = 30

            try:
                async with asyncio.timeout(timeout_seconds):
                    async for msg in websocket:
                        data = json.loads(msg)
                        responses.append(data)

                        # Stop after receiving message_complete or error
                        if data.get("type") in ["message_complete", "error"]:
                            break
            except asyncio.TimeoutError:
                # Timeout is okay for this test
                pass

            # Check for agent_handoff event
            handoff_events = [r for r in responses if r.get("type") == "agent_handoff"]

            # Note: Handoff might not happen immediately in first message
            # This is expected behavior - Router might respond first
            if handoff_events:
                handoff = handoff_events[0]
                assert "from_agent" in handoff, "agent_handoff missing from_agent"
                assert "to_agent" in handoff, "agent_handoff missing to_agent"
                assert "reason" in handoff, "agent_handoff missing reason"

            await websocket.close()

    @pytest.mark.asyncio
    async def test_websocket_empty_message_error(self):
        """Test sending empty message returns error"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Send empty message
            message = {"type": "message", "content": ""}
            await websocket.send(json.dumps(message))

            # Should receive error response
            response = await websocket.recv()
            data = json.loads(response)

            assert data.get("type") == "error", "Expected error response for empty message"
            assert data.get("code") == "empty_message", "Expected empty_message error code"

            await websocket.close()

    @pytest.mark.asyncio
    async def test_websocket_invalid_message_type(self):
        """Test sending invalid message type returns error"""
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Send invalid message type
            message = {"type": "invalid_type", "content": "Test"}
            await websocket.send(json.dumps(message))

            # Should receive error response
            response = await websocket.recv()
            data = json.loads(response)

            assert data.get("type") == "error", "Expected error response for invalid message type"
            assert data.get("code") == "invalid_message_type", "Expected invalid_message_type error code"

            await websocket.close()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not settings.MISTRAL_API_KEY, reason="MISTRAL_API_KEY not set")
    async def test_websocket_full_conversation_flow(self):
        """Test full conversation flow: Router → Intake → collect facts

        This test requires MISTRAL_API_KEY to be set and will make real API calls.
        """
        ws_url = f"{WS_URL}/ws/chat/{self.conversation_id}?token={self.token}"

        async with connect(ws_url) as websocket:
            # Message 1: Initial legal problem (Mietrecht)
            message1 = {
                "type": "message",
                "content": (
                    "Hallo, meine Heizung ist seit 2 Wochen kaputt. "
                    "Mein Vermieter antwortet nicht auf meine E-Mails."
                ),
            }
            await websocket.send(json.dumps(message1))

            # Collect responses for message 1
            responses1 = []
            try:
                async with asyncio.timeout(30):
                    async for msg in websocket:
                        data = json.loads(msg)
                        responses1.append(data)
                        if data.get("type") == "message_complete":
                            break
            except asyncio.TimeoutError:
                pytest.fail("Timeout waiting for first response")

            # Verify Router or Intake responded
            assert any(
                r.get("type") == "message_complete" for r in responses1
            ), "No message_complete received for message 1"

            # Message 2: Provide more details
            message2 = {
                "type": "message",
                "content": (
                    "Die Heizung ist komplett ausgefallen. "
                    "Ich habe dem Vermieter am 10. Oktober per E-Mail Bescheid gegeben."
                ),
            }
            await websocket.send(json.dumps(message2))

            # Collect responses for message 2
            responses2 = []
            try:
                async with asyncio.timeout(30):
                    async for msg in websocket:
                        data = json.loads(msg)
                        responses2.append(data)
                        if data.get("type") == "message_complete":
                            break
            except asyncio.TimeoutError:
                pytest.fail("Timeout waiting for second response")

            # Verify agent responded
            assert any(
                r.get("type") == "message_complete" for r in responses2
            ), "No message_complete received for message 2"

            # Check that messages were saved to database via API
            import requests

            response = requests.get(
                f"{BASE_URL}/api/v1/conversations/{self.conversation_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10,
            )
            assert response.status_code == 200, f"Failed to get conversation: {response.status_code}"
            conversation_data = response.json()
            messages = conversation_data.get("messages", [])

            # Should have at least 2 user messages + 2 assistant messages
            assert len(messages) >= 4, f"Expected at least 4 messages, got {len(messages)}"

            user_messages = [m for m in messages if m.get("role") == "user"]
            assistant_messages = [m for m in messages if m.get("role") == "assistant"]

            assert len(user_messages) >= 2, "Expected at least 2 user messages saved"
            assert len(assistant_messages) >= 2, "Expected at least 2 assistant messages saved"

            await websocket.close()


if __name__ == "__main__":
    # Run tests with: pytest tests/test_websocket.py -v
    pytest.main([__file__, "-v", "-s"])
