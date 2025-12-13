#!/usr/bin/env python3
"""Manual WebSocket Test Script

Tests the WebSocket endpoint against the running Docker container.
This script creates a real user and conversation in the sumii_dev database.

Usage:
    python manual_test_websocket.py
"""

import asyncio
import json
import time

import httpx
from websockets import connect

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000"

TEST_USER = {
    "email": f"manual-test-{int(time.time())}@sumii.de",
    "password": "TestPassword123!",
}


async def main():
    print("=" * 80)
    print("Sumii WebSocket Manual Test")
    print("=" * 80)

    # Step 1: Register user
    print("\n[1] Registering test user...")
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/api/v1/auth/register", json=TEST_USER)
        if response.status_code != 201:
            print(f"❌ Registration failed: {response.text}")
            return
        print(f"✅ User registered: {TEST_USER['email']}")

        # Step 2: Login
        print("\n[2] Logging in...")
        response = await client.post(f"{BASE_URL}/api/v1/auth/login", json=TEST_USER)
        if response.status_code != 200:
            print(f"❌ Login failed: {response.text}")
            return
        token = response.json()["access_token"]
        print("✅ Login successful, got JWT token")

        # Step 3: Create conversation via API
        print("\n[3] Creating conversation via API...")
        response = await client.post(
            f"{BASE_URL}/api/v1/conversations",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Manual Test - Mietrecht"},
        )
        if response.status_code != 201:
            print(f"❌ Conversation creation failed: {response.text}")
            return
        conversation_data = response.json()
        conversation_id = conversation_data["id"]
        print(f"✅ Conversation created: {conversation_id}")

    # Step 4: Connect to WebSocket
    print("\n[4] Connecting to WebSocket...")
    ws_url = f"{WS_URL}/ws/chat/{conversation_id}?token={token}"

    try:
        async with connect(ws_url) as websocket:
            print("✅ WebSocket connected!")

            # Step 5: Send test message
            print("\n[5] Sending test message (German legal question - Mietrecht)...")
            message = {
                "type": "message",
                "content": "Hallo, meine Heizung ist seit 2 Wochen kaputt und mein Vermieter reagiert nicht.",
            }
            await websocket.send(json.dumps(message))
            print(f"✅ Sent: {message['content'][:60]}...")

            # Step 6: Receive responses
            print("\n[6] Receiving responses (waiting for handoffs)...")
            print("-" * 80)

            response_count = 0
            messages_complete = 0
            max_messages = 3  # Expect Router → Intake (1 handoff + 2 messages = good test)

            async for msg in websocket:
                response_count += 1
                data = json.loads(msg)
                event_type = data.get("type")

                if event_type == "agent_start":
                    agent = data.get("agent")
                    print(f"\n🤖 Agent Started: {agent}")

                elif event_type == "message_chunk":
                    content = data.get("content", "")
                    print(content, end="", flush=True)

                elif event_type == "message_complete":
                    messages_complete += 1
                    print(f"\n\n✅ Message Complete ({messages_complete}/{max_messages})")
                    print(f"   Agent: {data.get('agent')}")
                    print(f"   Message ID: {data.get('message_id')}")
                    print(f"   Content Length: {len(data.get('content', ''))} chars")

                    # Exit after receiving enough messages (allows testing handoffs)
                    if messages_complete >= max_messages:
                        print(f"\n✅ Received {max_messages} messages (including handoffs), stopping test")
                        break

                elif event_type == "agent_handoff":
                    from_agent = data.get("from_agent")
                    to_agent = data.get("to_agent")
                    print(f"\n\n🔄 HANDOFF: {from_agent} → {to_agent}")
                    # Continue listening - next agent will start

                elif event_type == "function_call":
                    function = data.get("function")
                    print(f"\n\n⚙️  Function Call: {function}")

                elif event_type == "error":
                    print(f"\n\n❌ Error: {data.get('error')}")
                    print(f"   Code: {data.get('code')}")
                    break

                # Safety timeout
                if response_count > 100:
                    print("\n\n⚠️  Response limit reached (100 events)")
                    break

            print("\n" + "-" * 80)
            print(f"\n✅ Test completed! Received {response_count} events")

            await websocket.close()

    except Exception as e:
        print(f"\n❌ WebSocket error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
