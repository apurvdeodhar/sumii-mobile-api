"""E2E Test: REST Conversation Creation + WebSocket Streaming Integration

Tests the complete flow:
1. Create conversation via REST API
2. Connect to WebSocket using that conversation
3. Send messages and receive streaming responses
4. Verify messages are saved to conversation

This validates the integration between REST API and WebSocket endpoints.
"""

import asyncio
import json
import time
from uuid import uuid4

import pytest
import requests
from websockets import connect

pytestmark = [pytest.mark.e2e, pytest.mark.requires_services, pytest.mark.requires_api]

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"


class TestRESTWebSocketIntegration:
    """E2E tests combining REST API and WebSocket"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test user and authentication for each test"""
        # Register user
        unique_email = f"e2e-rest-ws-{int(time.time() * 1000)}@sumii.de"
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

        # Login to get token (fastapi-users uses form data, not JSON)
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": unique_email, "password": "SecurePassword123!"},  # Form data
            timeout=10,
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        yield

        # Cleanup: Delete any conversations created
        try:
            response = requests.get(f"{BASE_URL}/api/v1/conversations", headers=self.headers, timeout=10)
            if response.status_code == 200:
                conversations = response.json()
                for conv in conversations:
                    requests.delete(
                        f"{BASE_URL}/api/v1/conversations/{conv['id']}",
                        headers=self.headers,
                        timeout=10,
                    )
        except Exception:
            pass  # Ignore cleanup errors

    @pytest.mark.asyncio
    async def test_create_conversation_via_rest_then_websocket_chat(self):
        """Test: Create conversation via REST, then use it for WebSocket chat"""
        # Step 1: Create conversation via REST API
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "E2E REST+WS Integration Test"},
            timeout=10,
        )
        assert response.status_code == 201, f"Failed to create conversation: {response.status_code} - {response.text}"
        conversation_data = response.json()
        conversation_id = conversation_data["id"]
        assert conversation_data["title"] == "E2E REST+WS Integration Test"
        assert conversation_data["status"] == "active"
        assert conversation_data["current_agent"] == "router"

        # Step 2: Verify conversation exists via REST API
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            timeout=10,
        )
        assert response.status_code == 200
        conv_data = response.json()
        assert conv_data["id"] == conversation_id
        assert len(conv_data["messages"]) == 0  # No messages yet

        # Step 3: Connect to WebSocket using the conversation ID
        ws_url = f"{WS_URL}/ws/chat/{conversation_id}?token={self.token}"
        async with connect(ws_url) as websocket:
            # Step 4: Send message via WebSocket
            message = {
                "type": "message",
                "content": "Hallo, ich habe ein Problem mit meiner Miete.",
            }
            await websocket.send(json.dumps(message))

            # Step 5: Collect streaming responses
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

            # Step 6: Verify WebSocket responses
            assert len(responses) > 0, "No responses received from WebSocket"

            # Check for agent_start event
            agent_start_events = [r for r in responses if r.get("type") == "agent_start"]
            assert len(agent_start_events) > 0, "No agent_start event received"
            assert agent_start_events[0]["agent"] == "router", "Expected Router agent to start"

            # Check for message chunks
            message_chunks = [r for r in responses if r.get("type") == "message_chunk"]
            assert len(message_chunks) > 0, "No message chunks received"

            # Check for message_complete
            complete_events = [r for r in responses if r.get("type") == "message_complete"]
            assert len(complete_events) > 0, "No message_complete event received"
            message_complete = complete_events[0]
            assert "message_id" in message_complete
            assert "content" in message_complete
            assert len(message_complete["content"]) > 0

            await websocket.close()

        # Step 7: Verify messages were saved to conversation via REST API
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            timeout=10,
        )
        assert response.status_code == 200
        conv_data = response.json()
        assert len(conv_data["messages"]) >= 2, "Expected at least 2 messages (user + AI)"

        # Verify user message
        user_messages = [m for m in conv_data["messages"] if m["role"] == "user"]
        assert len(user_messages) > 0, "User message not saved"
        assert user_messages[0]["content"] == "Hallo, ich habe ein Problem mit meiner Miete."

        # Verify AI message
        ai_messages = [m for m in conv_data["messages"] if m["role"] == "assistant"]
        assert len(ai_messages) > 0, "AI message not saved"
        assert len(ai_messages[0]["content"]) > 0, "AI message content is empty"
        assert ai_messages[0]["content"] == message_complete["content"], "AI message content mismatch"

    @pytest.mark.asyncio
    async def test_multiple_messages_via_websocket_then_verify_via_rest(self):
        """Test: Send multiple messages via WebSocket, verify all saved via REST"""
        # Step 1: Create conversation via REST
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Multi-message E2E Test"},
            timeout=10,
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Step 2: Connect to WebSocket and send multiple messages
        ws_url = f"{WS_URL}/ws/chat/{conversation_id}?token={self.token}"
        async with connect(ws_url) as websocket:
            messages_sent = [
                "Hallo, ich habe ein Problem.",
                "Meine Heizung funktioniert nicht.",
                "Was kann ich tun?",
            ]

            all_responses = []

            for i, msg_content in enumerate(messages_sent):
                # Send message
                message = {"type": "message", "content": msg_content}
                await websocket.send(json.dumps(message))

                # Collect responses for this message
                message_responses = []
                try:
                    async with asyncio.timeout(30):
                        async for msg in websocket:
                            data = json.loads(msg)
                            message_responses.append(data)
                            all_responses.append(data)

                            if data.get("type") == "message_complete":
                                break
                except asyncio.TimeoutError:
                    pytest.fail(f"Timeout waiting for response to message {i+1}")

                # Verify we got a response
                assert len(message_responses) > 0, f"No response to message {i+1}"
                complete_events = [r for r in message_responses if r.get("type") == "message_complete"]
                assert len(complete_events) > 0, f"No message_complete for message {i+1}"

            await websocket.close()

        # Step 3: Verify all messages saved via REST API
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            timeout=10,
        )
        assert response.status_code == 200
        conv_data = response.json()

        # Should have 3 user messages + 3 AI messages = 6 total
        assert len(conv_data["messages"]) >= 6, f"Expected at least 6 messages, got {len(conv_data['messages'])}"

        # Verify all user messages are present
        user_messages = [m for m in conv_data["messages"] if m["role"] == "user"]
        assert len(user_messages) == 3, f"Expected 3 user messages, got {len(user_messages)}"
        user_contents = [m["content"] for m in user_messages]
        for msg in messages_sent:
            assert msg in user_contents, f"User message '{msg}' not found in saved messages"

        # Verify all AI messages are present
        ai_messages = [m for m in conv_data["messages"] if m["role"] == "assistant"]
        assert len(ai_messages) == 3, f"Expected 3 AI messages, got {len(ai_messages)}"
        for ai_msg in ai_messages:
            assert len(ai_msg["content"]) > 0, "AI message has empty content"

    @pytest.mark.asyncio
    async def test_conversation_update_via_rest_after_websocket_chat(self):
        """Test: Update conversation metadata via REST after WebSocket chat"""
        # Step 1: Create conversation via REST
        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=self.headers,
            json={"title": "Update After Chat Test"},
            timeout=10,
        )
        assert response.status_code == 201
        conversation_id = response.json()["id"]

        # Step 2: Send message via WebSocket
        ws_url = f"{WS_URL}/ws/chat/{conversation_id}?token={self.token}"
        async with connect(ws_url) as websocket:
            message = {"type": "message", "content": "Ich brauche Hilfe mit Mietrecht."}
            await websocket.send(json.dumps(message))

            # Wait for response
            try:
                async with asyncio.timeout(30):
                    async for msg in websocket:
                        data = json.loads(msg)
                        if data.get("type") == "message_complete":
                            break
            except asyncio.TimeoutError:
                pass  # Continue even if timeout

            await websocket.close()

        # Step 3: Update conversation metadata via REST
        response = requests.patch(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            json={
                "legal_area": "Mietrecht",
                "case_strength": "strong",
                "urgency": "immediate",
            },
            timeout=10,
        )
        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["legal_area"] == "Mietrecht"
        assert updated_data["case_strength"] == "strong"
        assert updated_data["urgency"] == "immediate"

        # Step 4: Verify conversation still has messages
        response = requests.get(
            f"{BASE_URL}/api/v1/conversations/{conversation_id}",
            headers=self.headers,
            timeout=10,
        )
        assert response.status_code == 200
        conv_data = response.json()
        assert len(conv_data["messages"]) >= 2, "Messages should still be present after update"

    @pytest.mark.asyncio
    async def test_websocket_with_nonexistent_conversation(self):
        """Test: WebSocket connection fails with non-existent conversation"""
        fake_conversation_id = str(uuid4())
        ws_url = f"{WS_URL}/ws/chat/{fake_conversation_id}?token={self.token}"

        with pytest.raises(Exception):  # WebSocket should reject connection
            async with connect(ws_url) as websocket:
                await websocket.ping()

    @pytest.mark.asyncio
    async def test_websocket_with_other_user_conversation(self):
        """Test: WebSocket connection fails with another user's conversation"""
        # Create another user and conversation
        other_email = f"other-ws-{int(time.time() * 1000)}@sumii.de"
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={"email": other_email, "password": "SecurePassword123!"},
            timeout=10,
        )
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/login",
            data={"username": other_email, "password": "SecurePassword123!"},  # fastapi-users uses form data
            timeout=10,
        )
        other_token = response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = requests.post(
            f"{BASE_URL}/api/v1/conversations",
            headers=other_headers,
            json={"title": "Other User's Conversation"},
            timeout=10,
        )
        other_conv_id = response.json()["id"]

        # Try to connect to other user's conversation
        ws_url = f"{WS_URL}/ws/chat/{other_conv_id}?token={self.token}"

        with pytest.raises(Exception):  # WebSocket should reject connection
            async with connect(ws_url) as websocket:
                await websocket.ping()
