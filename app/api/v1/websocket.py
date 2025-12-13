"""WebSocket Chat Endpoint - Real-time communication with Mistral AI Agents

This endpoint handles real-time chat between users and AI agents.
It uses Mistral's Conversations API with agent handoffs.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from mistralai import Mistral
from mistralai.extra.run.context import RunContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Conversation, Message, MessageRole, User
from app.services.agents import MistralAgentsService, get_mistral_agents_service
from app.utils.security import verify_token_ws

router = APIRouter()


async def process_with_agents(
    websocket: WebSocket,
    conversation: Conversation,
    user_message_content: str,
    agents_service: MistralAgentsService,
    db: AsyncSession,
):
    """Process user message with Mistral Agents using Conversations API

    This function uses Mistral's Conversations API with RunContext for agent orchestration.
    Mistral handles handoffs automatically (handoff_execution="server").

    Args:
        websocket: WebSocket connection
        conversation: Current conversation model
        user_message_content: User's message text
        agents_service: Mistral agents service
        db: Database session
    """
    try:
        # Initialize Mistral client
        client = Mistral(api_key=settings.MISTRAL_API_KEY)

        # Always start with Router Agent (agent-driven routing)
        router_id = agents_service.get_agent_id("router")

        if not router_id:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": "Router agent not initialized",
                    "code": "agent_not_found",
                }
            )
            return

        # Track current agent for database updates
        current_agent_name = "router"
        full_response_parts = []

        # Send agent_start event
        agent_start_payload = {
            "type": "agent_start",
            "agent": current_agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_json(agent_start_payload)

        # Use RunContext for conversation lifecycle management
        async with RunContext(agent_id=router_id) as run_ctx:
            # Stream conversation with automatic handoffs
            stream = await client.beta.conversations.run_stream_async(
                run_ctx=run_ctx,
                inputs=user_message_content,
            )

            # Process events from conversation stream
            async for event in stream:
                # Handle different event types
                match event.event:
                    case "agent.handoff.started":
                        # Handoff initiated by agent
                        previous_agent = event.data.previous_agent_name
                        await websocket.send_json(
                            {
                                "type": "agent_handoff_started",
                                "from_agent": previous_agent,
                                "timestamp": event.data.created_at.isoformat(),
                            }
                        )

                    case "agent.handoff.done":
                        # Handoff completed, new agent active
                        next_agent = event.data.next_agent_name
                        current_agent_name = (
                            next_agent.lower().replace(" ", "_").replace("legal_", "")
                        )  # Map to our names
                        await websocket.send_json(
                            {
                                "type": "agent_handoff_done",
                                "to_agent": next_agent,
                                "timestamp": event.data.created_at.isoformat(),
                            }
                        )

                    case "message.output.delta":
                        # Stream agent response chunks
                        content = event.data.content
                        if content:
                            full_response_parts.append(content)
                            await websocket.send_json(
                                {"type": "message_chunk", "content": content, "agent": current_agent_name}
                            )

                    case "conversation.response.done":
                        # Conversation complete
                        break

                    case "conversation.response.error":
                        # Handle errors
                        error_msg = event.data.error if hasattr(event.data, "error") else "Unknown error"
                        await websocket.send_json(
                            {
                                "type": "error",
                                "error": error_msg,
                                "code": "conversation_error",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        return

        # Combine response chunks
        full_response = "".join(full_response_parts)

        # Save AI message to database
        if full_response:
            ai_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=full_response,
                agent_name=current_agent_name,
            )
            db.add(ai_message)
            await db.commit()
            await db.refresh(ai_message)

            # Send message complete event
            await websocket.send_json(
                {
                    "type": "message_complete",
                    "message_id": str(ai_message.id),
                    "content": full_response,
                    "agent": current_agent_name,
                    "timestamp": ai_message.created_at.isoformat(),
                }
            )

        # Update conversation metadata
        conversation.current_agent = current_agent_name
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()

    except Exception as e:
        # Handle errors gracefully
        await websocket.send_json(
            {
                "type": "error",
                "error": str(e),
                "code": "agent_processing_error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for real-time chat with Mistral AI agents

    Authentication: Pass JWT token as query parameter (?token=xxx)

    Message Format (Client → Server):
    {
        "type": "message",
        "content": "User's message text"
    }

    Event Formats (Server → Client):

    1. Agent Start:
    {
        "type": "agent_start",
        "agent": "intake",
        "timestamp": "2025-01-25T10:00:00Z"
    }

    2. Message Chunk (streaming):
    {
        "type": "message_chunk",
        "content": "Das tut",
        "agent": "intake"
    }

    3. Message Complete:
    {
        "type": "message_complete",
        "message_id": "uuid",
        "content": "Full message text",
        "agent": "intake",
        "timestamp": "2025-01-25T10:00:05Z"
    }

    4. Agent Handoff:
    {
        "type": "agent_handoff",
        "from_agent": "intake",
        "to_agent": "reasoning",
        "reason": "Facts collection complete",
        "timestamp": "2025-01-25T10:05:00Z"
    }

    5. Function Call:
    {
        "type": "function_call",
        "function": "extract_facts",
        "arguments": {...},
        "timestamp": "2025-01-25T10:05:05Z"
    }

    6. Error:
    {
        "type": "error",
        "error": "Error description",
        "code": "error_code",
        "timestamp": "2025-01-25T10:05:10Z"
    }
    """
    # Verify JWT token
    try:
        payload = verify_token_ws(token)
        user_email = payload.get("sub")
        if not user_email:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    # Get user from database

    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
        return

    # Get conversation and verify ownership
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="Invalid conversation ID")
        return

    result = await db.execute(select(Conversation).where(Conversation.id == conversation_uuid))
    conversation = result.scalar_one_or_none()

    if not conversation:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="Conversation not found")
        return

    if conversation.user_id != user.id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not your conversation")
        return

    # Accept WebSocket connection
    await websocket.accept()

    # Get Mistral Agents service
    agents_service = get_mistral_agents_service()

    # Initialize agents if not already initialized
    if not agents_service.agents:
        await agents_service.initialize_all_agents()

    try:
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            # Validate message format
            if data.get("type") != "message":
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": "Invalid message type",
                        "code": "invalid_message_type",
                    }
                )
                continue

            user_message_content = data.get("content", "").strip()
            if not user_message_content:
                await websocket.send_json({"type": "error", "error": "Empty message", "code": "empty_message"})
                continue

            # Save user message to database
            user_message = Message(conversation_id=conversation.id, role=MessageRole.USER, content=user_message_content)
            db.add(user_message)
            await db.commit()

            # Process message with Mistral Agents (using Conversations API)
            await process_with_agents(
                websocket=websocket,
                conversation=conversation,
                user_message_content=user_message_content,
                agents_service=agents_service,
                db=db,
            )

    except WebSocketDisconnect:
        # Client disconnected
        pass
    except Exception as e:
        # Unexpected error
        await websocket.send_json({"type": "error", "error": str(e), "code": "internal_error"})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
