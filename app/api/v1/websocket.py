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
    ResponseDoneEvent,
    ResponseErrorEvent,
    ToolExecutionDoneEvent,
    ToolExecutionStartedEvent,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Conversation, Document, Message, MessageRole, ThinkingBlock, User
from app.services.agents import MistralAgentsService, get_mistral_agents_service
from app.utils.security import verify_token_ws

logger = logging.getLogger(__name__)

router = APIRouter()


def get_thinking_description(agent: str, lang: str = "de") -> str:
    """Get a human-readable description for the thinking bubble based on agent name.

    Args:
        agent: The normalized agent name (e.g., 'router', 'intake', 'reasoning')
        lang: Language code ('de' or 'en')

    Returns:
        Localized description string for the ThinkingBubble preview
    """
    descriptions = {
        "de": {
            "router": "Analysiere Ihre Anfrage...",
            "intake": "Erfasse die relevanten Fakten...",
            "fact_completion": "Sammle weitere Details...",
            "reasoning": "Wende rechtliche Analyse an...",
            "wrapup": "Bereite Zusammenfassung vor...",
            "wrap_up": "Bereite Zusammenfassung vor...",
            "summary": "Erstelle Ihre Fallzusammenfassung...",
        },
        "en": {
            "router": "Analyzing your request...",
            "intake": "Collecting relevant facts...",
            "fact_completion": "Gathering additional details...",
            "reasoning": "Applying legal analysis...",
            "wrapup": "Preparing wrap-up...",
            "wrap_up": "Preparing wrap-up...",
            "summary": "Creating your case summary...",
        },
    }
    lang_dict = descriptions.get(lang, descriptions["de"])
    agent_lower = agent.lower()
    for key, value in lang_dict.items():
        if key in agent_lower:
            return value
    return "Verarbeite..." if lang == "de" else "Processing..."


def normalize_agent_id(agent: str) -> str:
    """Normalize agent name to standard agent_id for steps tracking."""
    lower = agent.lower().replace("_", "").replace("agent", "")
    if "router" in lower:
        return "router"
    if "intake" in lower:
        return "intake"
    if "fact" in lower or "completion" in lower:
        return "fact_completion"
    if "reasoning" in lower or "logic" in lower:
        return "reasoning"
    if "wrap" in lower or "up" in lower:
        return "wrapup"
    if "summary" in lower:
        return "summary"
    return "router"


async def create_thinking_block(db: AsyncSession, conversation_id: UUID, agent: str, title: str) -> ThinkingBlock:
    """Create a new ThinkingBlock and persist to database."""
    agent_id = normalize_agent_id(agent)
    thinking_block = ThinkingBlock(
        conversation_id=conversation_id,
        current_agent=agent,
        completed_agents=[],
        steps=[
            {
                "agent_id": agent_id,
                "title": title,
                "status": "active",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        is_generating_summary=False,
        is_live=True,
    )
    db.add(thinking_block)
    await db.commit()
    await db.refresh(thinking_block)
    return thinking_block


async def add_or_update_step(
    db: AsyncSession, thinking_block: ThinkingBlock, agent: str, title: str, status: str = "active"
) -> None:
    """Add or update a step in the ThinkingBlock."""
    agent_id = normalize_agent_id(agent)
    steps = list(thinking_block.steps) if thinking_block.steps else []

    # Check if step for this agent exists
    existing_idx = next((i for i, s in enumerate(steps) if s.get("agent_id") == agent_id), None)

    step_data = {
        "agent_id": agent_id,
        "title": title,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if existing_idx is not None:
        steps[existing_idx] = step_data
    else:
        steps.append(step_data)

    thinking_block.steps = steps
    thinking_block.current_agent = agent
    await db.commit()


async def complete_agent_step(db: AsyncSession, thinking_block: ThinkingBlock, agent: str) -> None:
    """Mark an agent's step as complete."""
    agent_id = normalize_agent_id(agent)
    steps = list(thinking_block.steps) if thinking_block.steps else []

    for step in steps:
        if step.get("agent_id") == agent_id:
            step["status"] = "complete"
            step["timestamp"] = datetime.now(timezone.utc).isoformat()

    thinking_block.steps = steps

    # Also add to completed_agents list
    completed = list(thinking_block.completed_agents) if thinking_block.completed_agents else []
    if agent not in completed:
        completed.append(agent)
    thinking_block.completed_agents = completed

    await db.commit()


async def _process_single_event(
    event,
    websocket: WebSocket,
    full_response_parts: list,
    current_agent_name: str,
    conversation=None,
    db: AsyncSession | None = None,
    thinking_block: ThinkingBlock | None = None,
    user_language: str = "de",
) -> str | tuple[str, str | None, str, str] | None:
    """Process a single Mistral event and return action indicator.

    Returns:
        None - normal event processed
        "handoff" - handoff event occurred
        "done" - stream complete
        "error" - error occurred
        ("function_call", tool_call_id, function_name, arguments) - function call to handle
    """
    # DEBUG: Log every event type received
    event_type_name = type(event.data).__name__ if hasattr(event, "data") else type(event).__name__
    logger.debug(f"[EVENT] Received event type: {event_type_name} (agent: {current_agent_name})")

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
            logger.info(f"🔄 [HANDOFF] {current_agent_name} → {next_agent_normalized} (raw: {next_agent})")
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
            # Send thinking_chunk for ThinkingBubble inline streaming
            next_thinking_title = get_thinking_description(next_agent_normalized, user_language)
            await websocket.send_json(
                {
                    "type": "thinking_chunk",
                    "content": next_thinking_title,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Update ThinkingBlock: complete old agent, add new agent step
            if db and thinking_block:
                await complete_agent_step(db, thinking_block, current_agent_name)
                await add_or_update_step(db, thinking_block, next_agent_normalized, next_thinking_title, "active")

            # Send reasoning_started event when handoff to reasoning logic agent
            if "reasoning" in next_agent_normalized and "logic" in next_agent_normalized:
                logger.debug("[REASONING] 🧠 Reasoning Logic Agent activated - will check for contradictions")
                await websocket.send_json(
                    {
                        "type": "reasoning_started",
                        "conversation_id": str(conversation.id) if conversation else None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                # Update conversation reasoning_started_at if available
                if conversation:
                    conversation.reasoning_started_at = datetime.now(timezone.utc)
                    logger.debug(f"[REASONING] Updated reasoning_started_at for conversation {conversation.id}")

            # Send wrapup_ready event when handoff to wrap-up agent for ThinkingBlocks
            if "wrap" in next_agent_normalized and "up" in next_agent_normalized:
                logger.debug("[WRAPUP] 📋 Wrap-Up Agent activated - ready for user confirmation")
                await websocket.send_json(
                    {
                        "type": "wrapup_ready",
                        "conversation_id": str(conversation.id) if conversation else None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

            # Log summary agent activation
            if "summary" in next_agent_normalized:
                logger.debug("[SUMMARY] 📄 Summary Agent activated - generating final summary")
                # Update conversation summary_started_at if available
                if conversation:
                    conversation.summary_started_at = datetime.now(timezone.utc)
                    logger.debug(f"[SUMMARY] Updated summary_started_at for conversation {conversation.id}")

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

        case ToolExecutionDoneEvent():
            # Tool execution completed
            tool_name = getattr(event.data, "name", "unknown")
            logger.info(f"✅ [TOOL_DONE] Tool execution completed: {tool_name}")
            await websocket.send_json(
                {
                    "type": "tool_execution_done",
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
            logger.info(f"🛠️ [FUNCTION_CALL] Agent {current_agent_name} calling: {function_name} (id: {tool_call_id})")
            logger.debug(
                f"[FUNCTION_CALL] Arguments: {arguments[:200]}..."
                if len(str(arguments)) > 200
                else f"[FUNCTION_CALL] Arguments: {arguments}"
            )
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
            error_code = getattr(event.data, "code", None)
            logger.error(f"❌ [RESPONSE_ERROR] Agent {current_agent_name}: {error_msg} (code: {error_code})")
            logger.debug(f"[RESPONSE_ERROR] Full event data: {event.data}")
            await websocket.send_json(
                {
                    "type": "error",
                    "error": str(error_msg),
                    "code": "conversation_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return "error"

        case ResponseDoneEvent():
            # CRITICAL: This event signals stream completion!
            logger.info("🏁 [STREAM] ResponseDoneEvent received - stream complete!")
            return "done"

        case _:
            # Unknown event type - check for completion indicators
            event_type = getattr(event, "event", "") or str(type(event.data))
            logger.debug(f"[EVENT] Unknown/other event type: {event_type}")
            if "done" in str(event_type).lower() or "complete" in str(event_type).lower():
                logger.debug(f"[EVENT] Stream completion detected via event type: {event_type}")
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

        # Log start of processing
        logger.info(f"{'='*60}")
        logger.info(f"🚀 [START] Processing message for conversation {conversation.id}")
        logger.info(f"    User message length: {len(user_message_content)} chars")
        logger.info(f"{'='*60}")

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

        # Send thinking_chunk for ThinkingBubble inline streaming
        thinking_title = get_thinking_description(current_agent_name, user_language)
        await websocket.send_json(
            {
                "type": "thinking_chunk",
                "content": thinking_title,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Create ThinkingBlock in database and persist first step
        thinking_block = await create_thinking_block(db, conversation.id, current_agent_name, thinking_title)

        # Check if we have an existing Mistral conversation to continue
        existing_conv_id = conversation.mistral_conversation_id
        logger.debug(f"[MISTRAL] Conversation {conversation.id}: existing_conv_id={existing_conv_id}")

        # Use correct API pattern from Mistral cookbooks:
        # - start_stream() for first message
        # - append_stream() for subsequent messages
        if existing_conv_id:
            # Continue existing conversation - context preserved
            logger.info(f"📤 [MISTRAL] Calling append_stream() for conv_id={existing_conv_id}")
            try:
                response = client.beta.conversations.append_stream(
                    conversation_id=existing_conv_id,
                    inputs=user_message_content,
                )
            except Exception as e:
                logger.error(f"❌ [MISTRAL] append_stream FAILED: {type(e).__name__}: {e}")
                # Check for 404 - conversation/agent expired (happens when agents are recreated)
                if "404" in str(e) or "not found" in str(e).lower() or "does not have a version" in str(e).lower():
                    logger.warning(
                        f"⚠️ [MISTRAL] Conversation {existing_conv_id} is stale (agents recreated). "
                        "Resetting and creating fresh conversation..."
                    )
                    # Clear the stale conversation ID and create a fresh one
                    conversation.mistral_conversation_id = None
                    await db.commit()
                    # Retry with start_stream to create a fresh Mistral conversation
                    logger.info(f"🔄 [MISTRAL] Retrying with start_stream() for router_id={router_id}")
                    response = client.beta.conversations.start_stream(
                        agent_id=router_id,
                        inputs=user_message_content,
                    )
                else:
                    raise
        else:
            # Start new conversation
            logger.info(f"🆕 [MISTRAL] Calling start_stream() with router_id={router_id}")
            response = client.beta.conversations.start_stream(
                agent_id=router_id,
                inputs=user_message_content,
            )

        # Process events from stream (using context manager like cookbook)
        # Track ALL function calls - agents can call multiple functions at once
        pending_function_calls: list[dict] = []  # Each: {tool_call_id, function_name, arguments}
        current_function_call: dict | None = None  # Currently accumulating function call
        event_count = 0  # Track for progress logging

        logger.info("📡 [STREAM] Starting stream processing...")

        with response as event_stream:
            # Capture conversation_id from first event (cookbook pattern line 138)
            first_event = next(iter(event_stream))
            if not existing_conv_id and hasattr(first_event.data, "conversation_id"):
                conversation.mistral_conversation_id = first_event.data.conversation_id
                logger.info(f"🔗 [MISTRAL] New conversation created: {conversation.mistral_conversation_id}")
                await db.commit()

            # Process first event
            first_result = await _process_single_event(
                first_event,
                websocket,
                full_response_parts,
                current_agent_name,
                conversation,
                db,
                thinking_block,
                user_language,
            )
            if isinstance(first_result, tuple) and first_result[0] == "function_call":
                current_function_call = {
                    "tool_call_id": first_result[1],
                    "function_name": first_result[2],
                    "arguments": first_result[3] or "",
                }

            # Process remaining events
            for event in event_stream:
                event_count += 1
                # Log progress every 50 events (to show system is alive during long streams)
                if event_count % 50 == 0:
                    logger.info(f"⏳ [STREAM] Progress: {event_count} events processed (agent: {current_agent_name})")

                result = await _process_single_event(
                    event,
                    websocket,
                    full_response_parts,
                    current_agent_name,
                    conversation,
                    db,
                    thinking_block,
                    user_language,
                )
                if result == "handoff":
                    # Update current agent from handoff
                    current_agent_name = getattr(event.data, "next_agent_name", current_agent_name)
                    current_agent_name = current_agent_name.lower().replace(" ", "_").replace("legal_", "")
                elif result == "done":
                    logger.info(f"✅ [STREAM] Stream complete after {event_count} events")
                    break
                elif result == "error":
                    logger.error(f"❌ [STREAM] Error after {event_count} events")
                    return
                elif isinstance(result, tuple) and result[0] == "function_call":
                    new_tool_call_id = result[1]
                    new_function_name = result[2]
                    new_arguments = result[3] or ""

                    # Check if this is a NEW function call or continuation of current one
                    if current_function_call is None:
                        # First function call
                        logger.debug(
                            f"[FUNC] NEW function call: {new_function_name}, args length: {len(new_arguments)}"
                        )
                        current_function_call = {
                            "tool_call_id": new_tool_call_id,
                            "function_name": new_function_name,
                            "arguments": new_arguments,
                        }
                    elif current_function_call["tool_call_id"] == new_tool_call_id:
                        # Continuing SAME function call - append arguments
                        current_function_call["arguments"] += new_arguments
                        logger.debug(
                            f"[FUNC] Accumulating {new_function_name} args: "
                            f"total {len(current_function_call['arguments'])} chars"
                        )
                    else:
                        # Different function - save old one, start new one
                        logger.info(
                            f"📦 [FUNC] Saved function call: {current_function_call['function_name']} "
                            f"(args: {len(current_function_call['arguments'])} chars)"
                        )
                        pending_function_calls.append(current_function_call)
                        current_function_call = {
                            "tool_call_id": new_tool_call_id,
                            "function_name": new_function_name,
                            "arguments": new_arguments,
                        }

            # Don't forget the last function call
            if current_function_call:
                pending_function_calls.append(current_function_call)
                logger.info(
                    f"📦 [FUNC] Saved final function call: {current_function_call['function_name']} "
                    f"(args: {len(current_function_call['arguments'])} chars)"
                )

        logger.info(
            f"📡 [STREAM] Stream ended. Total events: {event_count}, Functions pending: {len(pending_function_calls)}"
        )

        # Handle ALL pending function calls (Mistral requires response for EACH call)
        # Track if summary generation should be triggered
        trigger_summary_generation = False
        summary_case_data = None

        function_results: list[FunctionResultEntry] = []

        if pending_function_calls:
            logger.info(f"{'='*40}")
            logger.info(f"🔧 [FUNC] Processing {len(pending_function_calls)} function call(s)...")
            logger.info(f"{'='*40}")

        for func_call in pending_function_calls:
            tool_call_id = func_call["tool_call_id"]
            function_name = func_call["function_name"]
            arguments = func_call["arguments"]

            logger.info(f"🔧 [FUNC] Processing: {function_name} (id: {tool_call_id})")

            # WRAP-UP: Handle signal_confirmation from Wrap-Up Agent
            if function_name == "signal_confirmation":
                logger.info(f"✅ [WRAPUP] signal_confirmation called for conversation {conversation.id}")
                try:
                    confirmation_data = json.loads(arguments) if arguments else {}
                    is_confirmed = confirmation_data.get("confirmed", False)
                    user_summary = confirmation_data.get("user_response_summary", "")
                    corrections = confirmation_data.get("corrections_needed", "")

                    logger.info(f"[WRAPUP] Confirmed: {is_confirmed}, Response: {user_summary}")

                    # Send confirmation event to client
                    await websocket.send_json(
                        {
                            "type": "confirmation_received",
                            "confirmed": is_confirmed,
                            "user_response": user_summary,
                            "corrections_needed": corrections if not is_confirmed else None,
                            "conversation_id": str(conversation.id),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse confirmation arguments: {e}")
                    logger.error(f"[CONFIRM] Raw args: {arguments[:200] if arguments else 'None'}")

            # WRAP-UP: Handle track_documents from Wrap-Up Agent
            elif function_name == "track_documents":
                logger.info(f"📋 [WRAPUP] track_documents called for conversation {conversation.id}")
                try:
                    document_tracking_data = json.loads(arguments) if arguments else {}
                    docs = document_tracking_data.get("documents", [])
                    missing = document_tracking_data.get("missing_critical_documents", [])
                    summary = document_tracking_data.get("evidence_summary", "")

                    logger.info(f"[WRAPUP] Tracked {len(docs)} documents, {len(missing)} missing")

                    # Store document tracking in conversation
                    if hasattr(conversation, "document_tracker"):
                        conversation.document_tracker = document_tracking_data

                    # Send document tracking event to client
                    await websocket.send_json(
                        {
                            "type": "documents_tracked",
                            "document_count": len(docs),
                            "missing_count": len(missing),
                            "evidence_summary": summary,
                            "conversation_id": str(conversation.id),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse document tracking arguments: {e}")
                    logger.error(f"[TRACK_DOCS] Raw args: {arguments[:200] if arguments else 'None'}")

            # Summary Agent: Handle generate_summary
            elif function_name == "generate_summary":
                logger.info(f"📝 AUTO-TRIGGER: Summary generation for conversation {conversation.id}")
                logger.debug(f"[SUMMARY] Arguments length: {len(arguments) if arguments else 0} chars")

                await websocket.send_json(
                    {
                        "type": "summary_generating",
                        "conversation_id": str(conversation.id),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                logger.debug("[SUMMARY] Sent summary_generating event to client")

                try:
                    summary_case_data = json.loads(arguments) if arguments else {}
                    trigger_summary_generation = True
                    logger.info(f"[SUMMARY] ✅ Data parsed, keys: {list(summary_case_data.keys())}")
                    logger.info(f"[SUMMARY] trigger_summary_generation={trigger_summary_generation}")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ [SUMMARY] Failed to parse summary arguments: {e}")
                    logger.error(f"[SUMMARY] Raw args: {arguments[:200] if arguments else 'None'}")

            # Build function result for this call
            function_results.append(
                FunctionResultEntry(
                    tool_call_id=tool_call_id,
                    result=f"Function {function_name} executed successfully. Data collected.",
                )
            )

        # Send ALL function results back to Mistral (if any)
        if function_results:
            logger.info(f"📤 [FUNC] Sending {len(function_results)} function result(s) back to Mistral")
            conv_id = conversation.mistral_conversation_id
            if conv_id:
                try:
                    logger.debug(f"[FUNC] Calling append_stream with conversation_id={conv_id[:20]}...")
                    continuation = client.beta.conversations.append_stream(
                        conversation_id=conv_id,
                        inputs=function_results,  # Send ALL results at once
                    )
                    logger.info("[FUNC] ✅ append_stream call succeeded, processing continuation events...")
                except Exception as e:
                    logger.error(f"❌ [MISTRAL] Function result append FAILED: {type(e).__name__}: {e}")
                    if "404" in str(e) or "not found" in str(e).lower() or "does not have a version" in str(e).lower():
                        logger.warning(
                            f"⚠️ [MISTRAL] Conversation {conv_id} is stale. Clearing ID but continuing execution."
                        )
                        conversation.mistral_conversation_id = None
                        await db.commit()
                        # Don't return - continue to process summary generation if triggered
                        logger.info(
                            "[MISTRAL] Skipping continuation stream, will process local functions (e.g. summary)"
                        )
                    else:
                        raise
                # Process continuation events
                with continuation as cont_stream:
                    for cont_event in cont_stream:
                        cont_result = await _process_single_event(
                            cont_event,
                            websocket,
                            full_response_parts,
                            current_agent_name,
                            conversation,
                            db,
                            thinking_block,
                            user_language,
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
            logger.info(f"{'='*60}")
            logger.info(f"✅ [END] Message complete for conversation {conversation.id}")
            logger.info(f"    Response length: {len(full_response)} chars, Agent: {current_agent_name}")
            logger.info(f"{'='*60}")

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

                # Add summary step to ThinkingBlock
                if thinking_block:
                    summary_title = get_thinking_description("summary", user_language)
                    await add_or_update_step(db, thinking_block, "summary", summary_title, "active")
                    # Send thinking_chunk for UI update
                    await websocket.send_json(
                        {
                            "type": "thinking_chunk",
                            "content": summary_title,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )

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

                    # Complete summary step and mark ThinkingBlock as finished
                    if thinking_block:
                        await complete_agent_step(db, thinking_block, "summary")
                        thinking_block.is_live = False
                        thinking_block.completed_at = datetime.now(timezone.utc)
                        await db.commit()

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
        import traceback

        logger.error(f"❌ [PROCESS_ERROR] Exception in process_with_agents: {type(e).__name__}: {e}")
        logger.error(
            f"[PROCESS_ERROR] Conversation: {conversation.id}, Mistral conv: {conversation.mistral_conversation_id}"
        )
        logger.debug(f"[PROCESS_ERROR] Traceback:\n{traceback.format_exc()}")
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
