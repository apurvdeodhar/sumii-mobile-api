"""WebSocket Chat Endpoint - Real-time communication with Mistral AI Agents

This endpoint handles real-time chat between users and AI agents.
It uses Mistral's Conversations API with agent handoffs.
"""

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from mistralai import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    FunctionResultEntry,
    MessageOutputEvent,
    Mistral,
    ResponseErrorEvent,
    ToolExecutionStartedEvent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Conversation, Document, Message, MessageRole, User
from app.services.agents import MistralAgentsService, get_mistral_agents_service
from app.utils.security import verify_token_ws

logger = logging.getLogger(__name__)

router = APIRouter()


async def _process_single_event(
    event, websocket: WebSocket, full_response_parts: list, current_agent_name: str, conversation=None
) -> str | tuple[str, str | None, str, str] | None:
    """Process a single Mistral event and return action indicator.

    Returns:
        None - normal event processed
        "handoff" - handoff event occurred
        "done" - stream complete
        "error" - error occurred
        ("function_call", tool_call_id, function_name, arguments) - function call to handle
    """
    # Use isinstance matching like the cookbook pattern
    match event.data:
        case MessageOutputEvent():
            # Handle message output
            content = event.data.content
            if content:
                # Content can be a list of chunks or a string
                if isinstance(content, list):
                    # Extract text from chunks
                    text_content = ""
                    for chunk in content:
                        if hasattr(chunk, "text"):
                            text_content += chunk.text
                        elif hasattr(chunk, "get"):
                            text_content += chunk.get("text", "")
                        elif isinstance(chunk, str):
                            text_content += chunk
                    content = text_content

                if content:
                    full_response_parts.append(content)
                    await websocket.send_json(
                        {"type": "message_chunk", "content": content, "agent": current_agent_name}
                    )
            return None

        case AgentHandoffDoneEvent():
            # Agent handed off to next agent
            next_agent = getattr(event.data, "next_agent_name", "unknown")
            # Normalize agent name: lowercase, underscores, remove prefixes
            next_agent_normalized = next_agent.lower().replace(" ", "_").replace("legal_", "")
            await websocket.send_json(
                {
                    "type": "agent_handoff",
                    "fromAgent": current_agent_name,
                    "toAgent": next_agent_normalized,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            # Also send agent_start for the new agent
            await websocket.send_json(
                {
                    "type": "agent_start",
                    "agent": next_agent_normalized,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Send wrapup_ready event when handoff to wrap-up agent for ThinkingBlocks
            if "wrap" in next_agent_normalized and "up" in next_agent_normalized:
                await websocket.send_json(
                    {
                        "type": "wrapup_ready",
                        "conversation_id": str(conversation.id) if conversation else None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

            return "handoff"

        case ToolExecutionStartedEvent():
            # Tool execution started
            tool_name = getattr(event.data, "name", "unknown")
            await websocket.send_json(
                {
                    "type": "tool_execution",
                    "tool": tool_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return None

        case FunctionCallEvent():
            # Agent is calling a function/tool - capture details
            tool_call_id = getattr(event.data, "tool_call_id", None)
            function_name = getattr(event.data, "name", "unknown")
            arguments = getattr(event.data, "arguments", "")
            await websocket.send_json(
                {
                    "type": "function_call",
                    "tool_call_id": tool_call_id,
                    "function": function_name,
                    "arguments": arguments,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            # Return special indicator for function call handling
            return ("function_call", tool_call_id, function_name, arguments)

        case ResponseErrorEvent():
            # Error occurred
            error_msg = getattr(event.data, "message", "Unknown error")
            await websocket.send_json(
                {
                    "type": "error",
                    "error": str(error_msg),
                    "code": "conversation_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return "error"

        case _:
            # Unknown event type - check for completion indicators
            event_type = getattr(event, "event", "") or str(type(event.data))
            if "done" in str(event_type).lower() or "complete" in str(event_type).lower():
                return "done"
            return None


async def process_with_agents(
    websocket: WebSocket,
    conversation: Conversation,
    user_message_content: str,
    agents_service: MistralAgentsService,
    db: AsyncSession,
    user_language: str = "de",
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
        user_language: User's preferred language code ("de" or "en")
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
        full_response_parts: list[str] = []

        # Prepend language instruction to ensure LLM responds in user's language
        lang_name = "German" if user_language == "de" else "English"
        language_instruction = f"IMPORTANT: You MUST respond in {lang_name} only.\n\n"
        user_message_content = language_instruction + user_message_content

        # Send agent_start event
        agent_start_payload = {
            "type": "agent_start",
            "agent": current_agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_json(agent_start_payload)

        # Check if we have an existing Mistral conversation to continue
        existing_conv_id = conversation.mistral_conversation_id

        # Use correct API pattern from Mistral cookbooks:
        # - start_stream() for first message
        # - append_stream() for subsequent messages
        if existing_conv_id:
            # Continue existing conversation - context preserved
            response = client.beta.conversations.append_stream(
                conversation_id=existing_conv_id,
                inputs=user_message_content,
            )
        else:
            # Start new conversation
            response = client.beta.conversations.start_stream(
                agent_id=router_id,
                inputs=user_message_content,
            )

        # Process events from stream (using context manager like cookbook)
        # Track function call accumulation (cookbook pattern from travel_assistant)
        pending_tool_call_id: str | None = None
        pending_function_name: str = ""
        pending_arguments: str = ""

        with response as event_stream:
            # Capture conversation_id from first event (cookbook pattern line 138)
            first_event = next(iter(event_stream))
            if not existing_conv_id and hasattr(first_event.data, "conversation_id"):
                conversation.mistral_conversation_id = first_event.data.conversation_id
                await db.commit()

            # Process first event
            first_result = await _process_single_event(
                first_event, websocket, full_response_parts, current_agent_name, conversation
            )
            if isinstance(first_result, tuple) and first_result[0] == "function_call":
                pending_tool_call_id = first_result[1]
                pending_function_name = first_result[2]
                pending_arguments += first_result[3] or ""

            # Process remaining events
            for event in event_stream:
                result = await _process_single_event(
                    event, websocket, full_response_parts, current_agent_name, conversation
                )
                if result == "handoff":
                    # Update current agent from handoff
                    current_agent_name = getattr(event.data, "next_agent_name", current_agent_name)
                    current_agent_name = current_agent_name.lower().replace(" ", "_").replace("legal_", "")
                elif result == "done":
                    break
                elif result == "error":
                    return
                elif isinstance(result, tuple) and result[0] == "function_call":
                    # Accumulate function call data (cookbook pattern line 174)
                    pending_tool_call_id = result[1]
                    pending_function_name = result[2]
                    pending_arguments += result[3] or ""

        # Handle pending function call AFTER stream completes (cookbook pattern lines 182-186)
        # Track if summary generation should be triggered
        trigger_summary_generation = False
        summary_case_data = None

        if pending_tool_call_id:
            # AUTO-TRIGGER: If Summary Agent called generate_summary, prepare for summary generation
            if pending_function_name == "generate_summary":
                logger.info(f"📝 AUTO-TRIGGER: Summary generation for conversation {conversation.id}")

                # Send "summary_generating" event to client
                await websocket.send_json(
                    {
                        "type": "summary_generating",
                        "conversation_id": str(conversation.id),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # Parse structured case data from function arguments
                try:
                    summary_case_data = json.loads(pending_arguments) if pending_arguments else {}
                    trigger_summary_generation = True
                    logger.info(f"Summary data keys: {list(summary_case_data.keys())}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse summary arguments: {e}")

            # Create function result (our functions are data collectors, return success)
            function_result = FunctionResultEntry(
                tool_call_id=pending_tool_call_id,
                result=f"Function {pending_function_name} executed successfully. Data collected.",
            )

            # Get conversation ID for append
            conv_id = conversation.mistral_conversation_id
            if conv_id:
                # Send function result back to conversation
                continuation = client.beta.conversations.append_stream(
                    conversation_id=conv_id,
                    inputs=[function_result],
                )
                # Process continuation events
                with continuation as cont_stream:
                    for cont_event in cont_stream:
                        cont_result = await _process_single_event(
                            cont_event, websocket, full_response_parts, current_agent_name, conversation
                        )
                        if cont_result == "handoff":
                            current_agent_name = getattr(cont_event.data, "next_agent_name", current_agent_name)
                            current_agent_name = current_agent_name.lower().replace(" ", "_").replace("legal_", "")
                        elif cont_result == "done":
                            break
                        elif cont_result == "error":
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

        # AUTO-GENERATE SUMMARY if trigger was set
        if trigger_summary_generation and summary_case_data:
            try:
                from app.models import Summary
                from app.services.pdf_service import PDFService
                from app.services.storage_service import StorageService
                from app.utils.reference_number import generate_sumii_reference_number

                logger.info(f"📄 Generating summary for conversation {conversation.id}")

                # Check if summary already exists
                existing_summary = await db.execute(select(Summary).where(Summary.conversation_id == conversation.id))
                if existing_summary.scalar_one_or_none():
                    logger.info("Summary already exists, skipping generation")
                else:
                    # Generate summary_id first, then reference number
                    from uuid import uuid4

                    summary_id = uuid4()
                    reference_number = generate_sumii_reference_number(summary_id)

                    # Get markdown from case_data or generate from conversation
                    markdown_content = summary_case_data.get("markdown_summary", "")
                    if not markdown_content:
                        markdown_content = (
                            f"# Fallzusammenfassung\n\n"
                            f"{json.dumps(summary_case_data, indent=2, ensure_ascii=False)}"
                        )

                    # Create PDF using PDFService
                    pdf_service = PDFService()
                    storage_service = StorageService()

                    # Prepare structured data for PDF
                    structured_data = summary_case_data.get("structured_case_data", summary_case_data)
                    pdf_content = pdf_service.template_to_pdf(structured_data, str(summary_id))

                    # Upload PDF to S3
                    pdf_s3_key, pdf_url = storage_service.upload_summary(
                        file_content=pdf_content,
                        reference_number=reference_number,
                        file_extension="pdf",
                        content_type="application/pdf",
                    )

                    # Upload markdown to S3
                    markdown_s3_key, _ = storage_service.upload_summary(
                        file_content=markdown_content.encode("utf-8"),
                        reference_number=reference_number,
                        file_extension="md",
                        content_type="text/markdown",
                    )

                    # Create Summary record
                    new_summary = Summary(
                        id=summary_id,
                        conversation_id=conversation.id,
                        user_id=conversation.user_id,
                        reference_number=reference_number,
                        markdown_content=markdown_content,
                        markdown_s3_key=markdown_s3_key,
                        pdf_s3_key=pdf_s3_key,
                        pdf_url=pdf_url,
                        legal_area=conversation.legal_area or "Other",
                        urgency=conversation.urgency or "months",
                    )
                    db.add(new_summary)

                    # Mark conversation as completed
                    from app.models.conversation import ConversationStatus

                    conversation.status = ConversationStatus.COMPLETED
                    conversation.summary_generated = True
                    await db.commit()
                    await db.refresh(new_summary)

                    # Send summary_ready event via WebSocket
                    await websocket.send_json(
                        {
                            "type": "summary_ready",
                            "summary_id": str(new_summary.id),
                            "reference_number": new_summary.reference_number,
                            "conversation_id": str(conversation.id),
                            "pdf_url": pdf_url,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    logger.info(f"✅ Summary {summary_id} created and sent to client")

            except Exception as e:
                logger.error(f"Failed to auto-generate summary: {e}")
                await websocket.send_json(
                    {
                        "type": "summary_error",
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

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
    # Verify JWT token (fastapi-users format: sub contains user ID UUID)
    try:
        payload = verify_token_ws(token)
        user_id_str = payload.get("sub")  # fastapi-users stores user ID (UUID) in 'sub'
        if not user_id_str:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return

        # Convert UUID string to UUID object
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid user ID in token")
            return
    except Exception as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Invalid token: {str(e)}")
        return

    # Get user from database by ID (fastapi-users uses ID, not email)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.unique().scalar_one_or_none()
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
    conversation = result.unique().scalar_one_or_none()

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

            # Parse document_ids from message (for file attachments)
            document_ids_raw = data.get("document_ids", [])
            document_ids: list[UUID] = []
            for did in document_ids_raw:
                try:
                    document_ids.append(UUID(did) if isinstance(did, str) else did)
                except (ValueError, TypeError):
                    pass  # Skip invalid UUIDs

            # Fetch document OCR text and augment message for LLM
            augmented_content = user_message_content
            if document_ids:
                docs_result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
                documents = docs_result.scalars().all()

                doc_context_parts = []
                for doc in documents:
                    if doc.ocr_text:
                        doc_context_parts.append(
                            f"--- BEGIN EXTRACTED CONTENT FROM '{doc.filename}' ---\n"
                            f"{doc.ocr_text}\n"
                            f"--- END EXTRACTED CONTENT ---"
                        )
                    else:
                        doc_context_parts.append(
                            f"[File attached: {doc.filename}] (No text content could be extracted from this file)"
                        )

                if doc_context_parts:
                    augmented_content = (
                        "IMPORTANT: The user has uploaded file(s). The text content has been automatically extracted "
                        "from these files using OCR and is provided below. You DO have access to this content - "
                        "please analyze the extracted text to answer the user's question.\n\n"
                        + "\n\n".join(doc_context_parts)
                        + "\n\n--- USER'S REQUEST ---\n"
                        + user_message_content
                    )

            # Save user message to database (with document_ids)
            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=user_message_content,
                document_ids=[str(did) for did in document_ids] if document_ids else None,
            )
            db.add(user_message)
            await db.commit()

            # DEBUG: Log augmented content being sent to LLM
            if document_ids:
                print("[WebSocket] Sending augmented content to LLM (first 500 chars):")
                print(augmented_content[:500] if len(augmented_content) > 500 else augmented_content)

            # Process message with Mistral Agents (using Conversations API)
            # Use augmented_content (with document context) for LLM
            await process_with_agents(
                websocket=websocket,
                conversation=conversation,
                user_message_content=augmented_content,
                agents_service=agents_service,
                db=db,
                user_language=user.language or "de",
            )

    except WebSocketDisconnect:
        # Client disconnected - this is normal, do nothing
        pass
    except Exception as e:
        # Log the error for debugging
        import traceback

        print(f"[WebSocket ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()

        # Unexpected error - try to send error to client if connection is still open
        try:
            await websocket.send_json({"type": "error", "error": str(e), "code": "internal_error"})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            # Connection already closed, nothing to do
            pass
