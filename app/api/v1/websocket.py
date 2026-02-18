"""WebSocket Chat Endpoint - Real-time communication with Mistral AI Agents

This endpoint handles real-time chat between users and AI agents.
It uses Mistral's Conversations API with agent handoffs.
"""

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from mistralai import (
    AgentHandoffDoneEvent,
    FunctionCallEvent,
    FunctionResultEntry,
    MessageOutputEvent,
    ResponseDoneEvent,
    ResponseErrorEvent,
    ToolExecutionDoneEvent,
    ToolExecutionStartedEvent,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models import Conversation, Document, Message, MessageRole, ThinkingSteps, User
from app.schemas.summary_validation import build_user_profile_context, validate_and_enrich_summary
from app.services.agents import MistralAgentsService, get_mistral_agents_service
from app.services.mistral_client import get_mistral_async_client
from app.utils.security import verify_token_ws

logger = logging.getLogger(__name__)

router = APIRouter()

# Patterns to replace leaked internal agent names with "Sumii" in user-facing text.
# Two tiers: (1) full "X Agent" names, (2) "I'm/I am X" without "Agent" suffix (catches split chunks).
_AGENT_NAME_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    # Full agent names → "Sumii"
    (
        re.compile(r"(?:Intake|Router|Summary|Wrap-?Up|Fact[\s-]?Completion|Reasoning[\s-]?Logic)\s*Agent", re.I),
        "Sumii",
    ),
    # "I'm/I am [role]" without Agent suffix → "I'm Sumii" (catches split-chunk leaks)
    (
        re.compile(r"I(?:'m| am) (?:the )?(?:Intake|Router|Summary|Wrap-?Up|Fact[\s-]?Completion|Reasoning)", re.I),
        "I'm Sumii",
    ),
    # German handoff leak
    (re.compile(r"an den \w+ Agent weiterleiten", re.I), ""),
    # "a Large Language Model (LLM) created by Mistral AI" → "your legal assistant"
    (
        re.compile(
            r",?\s*a Large Language Model\s*(?:\(LLM\))?\s*(?:created|made|built|developed) by Mistral AI", re.I
        ),
        ", your legal assistant",
    ),
    # "I don't have the necessary context/tools" refusal → redirect to helpful question
    (
        re.compile(
            r"I(?:'m sorry|apologize),?\s*(?:but )?I (?:don't|do not) have the necessary (?:context|tools|information)"
            r"[^.]*\.",
            re.I,
        ),
        "Let me continue helping you.",
    ),
]


def sanitize_agent_text(text: str) -> str:
    """Replace leaked internal agent names and model identity with 'Sumii' in user-facing text."""
    result = text
    for pattern, replacement in _AGENT_NAME_REPLACEMENTS:
        result = pattern.sub(replacement, result)
    return result


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
    if "wrap" in lower or "wrapup" in lower:
        return "wrapup"
    if "summary" in lower:
        return "summary"
    return "router"


def serialize_for_json(obj: Any) -> Any:
    """Safely serialize Mistral SDK objects (Pydantic models) to JSON-compatible types.

    Handles ThinkChunk, TextChunk, and other Mistral SDK objects that have model_dump().
    Recursively processes dicts and lists.

    Args:
        obj: Any object that might contain Mistral SDK Pydantic models

    Returns:
        JSON-serializable version of the object
    """
    if obj is None:
        return None

    # Handle Pydantic models (ThinkChunk, TextChunk, etc.)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()

    # Handle dicts recursively
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}

    # Handle lists recursively
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]

    # Handle tuples
    if isinstance(obj, tuple):
        return tuple(serialize_for_json(item) for item in obj)

    # Primitive types (str, int, float, bool) pass through
    return obj


async def get_or_create_thinking_steps(
    db: AsyncSession, conversation_id: UUID, agent: str, title: str, message_id: UUID | None = None
) -> ThinkingSteps:
    """Get existing ThinkingSteps for this message, or create a new one.

    Per-Message Pattern: Each user message gets its own ThinkingSteps record.
    This enables UI to show a ThinkingBubble per turn in multi-turn conversations.

    If message_id is provided:
      - Look for existing ThinkingSteps with that message_id
      - If found, update it; if not, create new

    If message_id is None (backwards compatibility):
      - Find any active (is_live=True) ThinkingSteps for conversation
      - If found, update it; if not, create new
    """
    from sqlalchemy import select, update

    agent_id = normalize_agent_id(agent)

    # Strategy 1: If message_id provided, find ThinkingSteps for that specific message
    if message_id:
        result = await db.execute(select(ThinkingSteps).where(ThinkingSteps.message_id == message_id).limit(1))
        existing_block = result.scalar_one_or_none()

        if existing_block:
            await add_or_update_step(db, existing_block, agent, title, "active")
            logger.debug(f"[ThinkingSteps] Updating existing block {existing_block.id} for message {message_id}")
            return existing_block

        # Close any previous live ThinkingSteps for this conversation
        await db.execute(
            update(ThinkingSteps)
            .where(ThinkingSteps.conversation_id == conversation_id)
            .where(ThinkingSteps.is_live == True)  # noqa: E712
            .values(is_live=False, completed_at=func.now())
        )
        await db.commit()

    else:
        # Backwards compatibility: find any active block for conversation
        result = await db.execute(
            select(ThinkingSteps)
            .where(ThinkingSteps.conversation_id == conversation_id)
            .where(ThinkingSteps.is_live == True)  # noqa: E712
            .order_by(ThinkingSteps.created_at.desc())
            .limit(1)
        )
        existing_block = result.scalar_one_or_none()

        if existing_block:
            await add_or_update_step(db, existing_block, agent, title, "active")
            logger.debug(
                f"[ThinkingSteps] Reusing existing block {existing_block.id} for conversation {conversation_id}"
            )
            return existing_block

    # Create new ThinkingSteps for this message
    thinking_steps = ThinkingSteps(
        conversation_id=conversation_id,
        message_id=message_id,
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
    db.add(thinking_steps)
    await db.commit()
    await db.refresh(thinking_steps)
    logger.debug(f"[ThinkingSteps] Created new block {thinking_steps.id} for message {message_id}")
    return thinking_steps


async def add_or_update_step(
    db: AsyncSession, thinking_steps: ThinkingSteps, agent: str, title: str, status: str = "active"
) -> None:
    """Add or update a step in the ThinkingSteps."""
    agent_id = normalize_agent_id(agent)
    steps = list(thinking_steps.steps) if thinking_steps.steps else []

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

    thinking_steps.steps = steps
    thinking_steps.current_agent = agent

    # Force SQLAlchemy to detect JSONB changes
    flag_modified(thinking_steps, "steps")

    await db.commit()


async def complete_agent_step(
    db: AsyncSession, thinking_steps: ThinkingSteps, agent: str, preview_text: str | None = None
) -> None:
    """Mark an agent's step as complete, optionally persisting preview text."""
    agent_id = normalize_agent_id(agent)
    steps = list(thinking_steps.steps) if thinking_steps.steps else []

    for step in steps:
        if step.get("agent_id") == agent_id:
            step["status"] = "complete"
            step["timestamp"] = datetime.now(timezone.utc).isoformat()
            if preview_text:
                step["preview_text"] = preview_text

    thinking_steps.steps = steps

    # Also add to completed_agents list
    completed = list(thinking_steps.completed_agents) if thinking_steps.completed_agents else []
    if agent not in completed:
        completed.append(agent)
    thinking_steps.completed_agents = completed

    # Force SQLAlchemy to detect JSONB changes (in-place mutations not tracked by default)
    flag_modified(thinking_steps, "steps")
    flag_modified(thinking_steps, "completed_agents")

    logger.info(f"[ThinkingSteps] Completed agent step: {agent}, completed_agents now: {completed}")

    await db.commit()


async def _process_single_event(
    event,
    websocket: WebSocket,
    full_response_parts: list,
    current_agent_name: str,
    conversation=None,
    db: AsyncSession | None = None,
    thinking_steps: ThinkingSteps | None = None,
    user_language: str = "de",
    stream_state: dict | None = None,
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
                # content can be: str, a single chunk object (ThinkChunk/TextChunk/etc.), or a list of chunks
                # Normalize to list for uniform processing
                chunks = content if isinstance(content, list) else [content]
                text_content = ""
                for chunk in chunks:
                    # Skip plain strings — add directly
                    if isinstance(chunk, str):
                        text_content += chunk
                        continue
                    # ThinkChunk: internal reasoning from Magistral — log but don't send to client
                    if hasattr(chunk, "thinking"):
                        for trace in getattr(chunk, "thinking", []):
                            if hasattr(trace, "text"):
                                logger.debug(f"[THINKING] Reasoning trace: {trace.text[:100]}...")
                        continue
                    # Dict with type "thinking" (alternate representation)
                    if hasattr(chunk, "get") and chunk.get("type") == "thinking":
                        for trace in chunk.get("thinking", []):
                            if isinstance(trace, dict) and trace.get("type") == "text":
                                logger.debug(f"[THINKING] Reasoning trace: {trace.get('text', '')[:100]}...")
                        continue
                    # TextChunk or any chunk with .text attribute
                    if hasattr(chunk, "text"):
                        text_content += chunk.text
                        continue
                    # Dict-like chunk with "text" key
                    if hasattr(chunk, "get"):
                        text_content += chunk.get("text", "")
                        continue
                    # Unknown chunk type — log warning instead of silently passing through
                    logger.warning(f"[EVENT] Unhandled chunk type: {type(chunk).__name__}, skipping")

                if text_content:
                    # Replace leaked agent names / model identity before sending to client
                    text_content = sanitize_agent_text(text_content)

                    if text_content.strip():
                        full_response_parts.append(text_content)
                        # Include agent_id from Mistral event for mobile routing
                        agent_id = getattr(event.data, "agent_id", None)
                        await websocket.send_json(
                            {
                                "type": "message_chunk",
                                "content": text_content,
                                "agent": current_agent_name,
                                "agent_id": str(agent_id) if agent_id else None,
                            }
                        )

                        # Send throttled thinking_preview for ThinkingBubble live streaming
                        if stream_state is not None:
                            stream_state["text_accumulator"] += text_content
                            stream_state["chunk_counter"] += 1
                            if stream_state["chunk_counter"] % 3 == 0:
                                await websocket.send_json(
                                    {
                                        "type": "thinking_preview",
                                        "agent": current_agent_name,
                                        "preview": stream_state["text_accumulator"][-120:],
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                    }
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

            # Persist current agent on conversation for correct tracking across messages
            if conversation:
                conversation.current_agent = next_agent_normalized
                db.add(conversation)

            # Update ThinkingSteps: complete old agent (with preview text), add new agent step
            if db and thinking_steps:
                # Persist accumulated text as preview_text for the completing agent
                preview = stream_state["text_accumulator"][-120:] if stream_state else None
                await complete_agent_step(db, thinking_steps, current_agent_name, preview_text=preview)
                await add_or_update_step(db, thinking_steps, next_agent_normalized, next_thinking_title, "active")

            # Reset stream_state accumulator for the next agent
            if stream_state is not None:
                stream_state["text_accumulator"] = ""
                stream_state["chunk_counter"] = 0

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

            # Send wrapup_ready event when handoff to wrap-up agent for ThinkingStepss
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
            logger.debug(f"🛠️ [FUNCTION_CALL] Agent {current_agent_name} calling: {function_name} (id: {tool_call_id})")
            logger.debug(
                f"[FUNCTION_CALL] Arguments: {arguments[:200]}..."
                if len(str(arguments)) > 200
                else f"[FUNCTION_CALL] Arguments: {arguments}"
            )
            # NOTE: We don't send function_call events to client anymore
            # Arguments stream in chunks (40+ events), flooding the client
            # Thinking blocks now use dedicated WS events instead
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


async def _handle_function_call(
    function_name: str,
    arguments: str,
    tool_call_id: str,
    conversation: Any,
    websocket: WebSocket,
    user: Any,
    logger: logging.Logger,
) -> tuple[FunctionResultEntry, dict | None, bool]:
    """Process a single function call and return the result to send back to Mistral.

    Handles signal_confirmation, track_documents, generate_summary, and
    any other function calls (check_completeness, etc.) generically.

    Returns:
        (result_entry, summary_case_data, trigger_summary)
        - result_entry: FunctionResultEntry to send back to Mistral
        - summary_case_data: parsed summary data if generate_summary, else None
        - trigger_summary: True if summary generation should be triggered
    """
    summary_case_data = None
    trigger_summary = False

    if function_name == "signal_confirmation":
        logger.info(f"✅ [WRAPUP] signal_confirmation called for conversation {conversation.id}")
        try:
            confirmation_data = json.loads(arguments) if arguments else {}
            is_confirmed = confirmation_data.get("confirmed", False)
            user_summary = confirmation_data.get("user_response_summary", "")
            corrections = confirmation_data.get("corrections_needed", "")

            logger.info(f"[WRAPUP] Confirmed: {is_confirmed}, Response: {user_summary}")

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

    elif function_name == "track_documents":
        logger.info(f"📋 [WRAPUP] track_documents called for conversation {conversation.id}")
        try:
            document_tracking_data = json.loads(arguments) if arguments else {}
            docs = document_tracking_data.get("documents", [])
            missing = document_tracking_data.get("missing_critical_documents", [])
            summary = document_tracking_data.get("evidence_summary", "")

            logger.info(f"[WRAPUP] Tracked {len(docs)} documents, {len(missing)} missing")

            if hasattr(conversation, "document_tracker"):
                conversation.document_tracker = document_tracking_data

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

        try:
            raw_args = json.loads(arguments) if arguments else {}
            validated = validate_and_enrich_summary(raw_args, user=user)
            summary_case_data = validated.model_dump()
            trigger_summary = True
            logger.info(f"[SUMMARY] ✅ Validated data, keys: {list(summary_case_data.keys())}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ [SUMMARY] Failed to parse summary arguments: {e}")
            logger.error(f"[SUMMARY] Raw args: {arguments[:200] if arguments else 'None'}")

    else:
        logger.info(f"🔧 [FUNC] Generic function call: {function_name}")

    result_entry = FunctionResultEntry(
        tool_call_id=tool_call_id,
        result=f"Function {function_name} executed successfully. Data collected.",
    )

    return result_entry, summary_case_data, trigger_summary


async def _generate_summary_background(
    conversation_id: UUID,
    user_id: UUID,
    summary_case_data: dict,
    user_language: str,
    thinking_steps_id: UUID | None,
    websocket: WebSocket | None = None,
) -> None:
    """Background task: Generate PDF summary, upload to S3, create DB record, send push notification.

    Runs independently of the WebSocket connection via asyncio.create_task().
    Uses its own DB session (cannot share with WS handler's session).
    Sends summary_ready event via WebSocket (if still connected) + push notification.
    """
    from app.database import AsyncSessionLocal
    from app.models import Summary
    from app.models.conversation import ConversationStatus
    from app.models.notification import Notification, NotificationType
    from app.models.user import User
    from app.services.pdf_service import PDFService
    from app.services.push_service import push_service
    from app.services.storage_service import StorageService
    from app.utils.reference_number import generate_sumii_reference_number

    async with AsyncSessionLocal() as db:
        try:
            # Re-fetch entities in this session's scope
            conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
            conversation = conv_result.unique().scalar_one_or_none()
            if not conversation:
                logger.error(f"Background summary: conversation {conversation_id} not found")
                return

            thinking_steps = None
            if thinking_steps_id:
                ts_result = await db.execute(select(ThinkingSteps).where(ThinkingSteps.id == thinking_steps_id))
                thinking_steps = ts_result.scalar_one_or_none()

            logger.info(f"📄 [BACKGROUND] Generating summary for conversation {conversation_id}")

            # Add summary step to ThinkingSteps
            if thinking_steps:
                summary_title = get_thinking_description("summary", user_language)
                await add_or_update_step(db, thinking_steps, "summary", summary_title, "active")

            # Check if summary already exists
            existing_summary = await db.execute(select(Summary).where(Summary.conversation_id == conversation_id))
            if existing_summary.scalar_one_or_none():
                logger.info("[BACKGROUND] Summary already exists, skipping generation")
                return

            # Generate summary_id first, then reference number
            from uuid import uuid4

            summary_id = uuid4()
            reference_number = generate_sumii_reference_number(summary_id)

            # Get markdown from case_data or generate from conversation
            markdown_content = summary_case_data.get("markdown_content", "")
            if not markdown_content:
                markdown_content = (
                    f"# Fallzusammenfassung\n\n"
                    f"{json.dumps(serialize_for_json(summary_case_data), indent=2, ensure_ascii=False)}"
                )

            # Create PDF using PDFService
            pdf_service = PDFService()
            storage_service = StorageService()

            # Fetch uploaded documents for this conversation (for PDF appendix)
            from app.models.document import Document, UploadStatus

            docs_result = await db.execute(
                select(Document)
                .where(
                    Document.conversation_id == conversation_id,
                    Document.upload_status == UploadStatus.COMPLETED,
                )
                .order_by(Document.created_at)
            )
            conversation_documents = docs_result.scalars().all()

            # Build attached_documents list for Anlage cover page in template
            attached_doc_info = [{"filename": doc.filename} for doc in conversation_documents]

            # Detect language from markdown content
            detected_language = "de"
            if markdown_content:
                german_indicators = ["Fallzusammenfassung", "Mandant", "Anspruchsteller", "Sachverhalt", "begehrt"]
                content_lower = markdown_content.lower()
                german_count = sum(1 for ind in german_indicators if ind.lower() in content_lower)
                detected_language = "de" if german_count >= 2 else "en"

            # Prepare structured data for PDF (already enriched by validate_and_enrich_summary)
            structured_data = summary_case_data.get("structured_case_data", summary_case_data)
            pdf_content = pdf_service.template_to_pdf(
                structured_data,
                str(summary_id),
                attached_documents=attached_doc_info if attached_doc_info else None,
                language=detected_language,
            )

            # Download and merge actual document pages into the PDF
            if conversation_documents:
                doc_contents: list[tuple[str, str, bytes]] = []
                for doc in conversation_documents:
                    try:
                        content = storage_service.download_document(doc.s3_key)
                        doc_contents.append((doc.filename, doc.file_type, content))
                    except Exception as dl_err:
                        logger.warning(f"[SUMMARY] Failed to download document {doc.id}: {dl_err}")

                if doc_contents:
                    pdf_content = pdf_service.merge_with_documents(pdf_content, doc_contents)
                    logger.info(f"[SUMMARY] Merged {len(doc_contents)} document(s) into summary PDF")

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
                conversation_id=conversation_id,
                user_id=user_id,
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
            conversation.status = ConversationStatus.COMPLETED
            conversation.summary_generated = True
            await db.commit()
            await db.refresh(new_summary)

            logger.info(f"✅ [BACKGROUND] Summary {summary_id} created")

            # Send summary_ready event via WebSocket (if still connected)
            if websocket:
                try:
                    await websocket.send_json(
                        {
                            "type": "summary_ready",
                            "summaryId": str(new_summary.id),
                            "conversationId": str(conversation_id),
                            "referenceNumber": reference_number,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    logger.info(f"[BACKGROUND] Sent summary_ready WS event for {summary_id}")
                except Exception:
                    logger.debug("[BACKGROUND] WS disconnected, summary_ready sent via push only")

            # Create Notification DB record + send push notification
            try:
                notif_title = "Zusammenfassung bereit" if user_language == "de" else "Summary ready"
                notif_message = (
                    "Ihre rechtliche Zusammenfassung ist verfügbar"
                    if user_language == "de"
                    else "Your legal summary is available"
                )
                notif_data = {
                    "summary_id": str(new_summary.id),
                    "conversation_id": str(conversation_id),
                }

                notification = Notification(
                    user_id=user_id,
                    type=NotificationType.SUMMARY_READY,
                    title=notif_title,
                    message=notif_message,
                    data=notif_data,
                )
                db.add(notification)
                await db.commit()

                # Fetch user for push token
                user_result = await db.execute(select(User).where(User.id == user_id))
                push_user = user_result.unique().scalar_one_or_none()
                if push_user:
                    await push_service.send_to_user(
                        push_user,
                        title=notif_title,
                        body=notif_message,
                        data=notif_data,
                    )
            except Exception as notif_err:
                logger.warning(f"[BACKGROUND] Push notification for summary failed: {notif_err}")

            # Complete summary step and mark ThinkingSteps as finished
            if thinking_steps:
                await complete_agent_step(db, thinking_steps, "summary")
                thinking_steps.is_live = False
                thinking_steps.completed_at = datetime.now(timezone.utc)
                await db.commit()

        except Exception as e:
            logger.error(f"[BACKGROUND] Failed to generate summary for conversation {conversation_id}: {e}")
            import traceback

            logger.debug(f"[BACKGROUND] Traceback:\n{traceback.format_exc()}")


async def _recover_from_stream_timeout(
    client,
    conversation: Conversation,
) -> str | None:
    """Check Mistral server-side history for a completed response after stream timeout.

    When a stream stalls (HTTP 200 but no SSE events), the response may have
    completed server-side. This function retrieves the conversation history
    to check for a completed MessageOutputEntry.

    Args:
        client: Mistral client instance (async-capable)
        conversation: Conversation with mistral_conversation_id set

    Returns:
        The recovered response text if a completed response is found, None otherwise.
    """
    conv_id = conversation.mistral_conversation_id
    if not conv_id:
        return None

    try:
        history = await client.beta.conversations.get_history_async(conversation_id=conv_id)
        if not history or not history.entries:
            logger.warning("[RECOVERY] No entries in conversation history")
            return None

        # Find the last MessageOutputEntry (assistant response)
        last_output = None
        for entry in reversed(history.entries):
            if getattr(entry, "type", "") == "message.output":
                last_output = entry
                break

        if not last_output:
            logger.warning("[RECOVERY] No assistant response found in history")
            return None

        # Check if it was completed
        if last_output.completed_at is None:
            logger.warning("[RECOVERY] Last assistant response is incomplete (completed_at=None)")
            return None

        # Extract text content from the completed response
        content = last_output.content
        if not content:
            return None

        if isinstance(content, str):
            logger.info(f"✅ [RECOVERY] Retrieved completed response ({len(content)} chars)")
            return content

        # Handle list of chunks (TextChunk, etc.)
        if isinstance(content, list):
            text_parts = []
            for chunk in content:
                if isinstance(chunk, str):
                    text_parts.append(chunk)
                elif hasattr(chunk, "text"):
                    text_parts.append(chunk.text)
            recovered = "".join(text_parts)
            if recovered:
                logger.info(f"✅ [RECOVERY] Retrieved completed response from chunks ({len(recovered)} chars)")
            return recovered or None

        # Single chunk with text attribute
        if hasattr(content, "text"):
            logger.info("✅ [RECOVERY] Retrieved completed response from single chunk")
            return content.text

        logger.warning(f"[RECOVERY] Unknown content type: {type(content).__name__}")
        return None

    except Exception as e:
        logger.error(f"[RECOVERY] Failed to retrieve conversation history: {e}")
        return None


async def process_with_agents(
    websocket: WebSocket,
    conversation: Conversation,
    user_message_content: str,
    agents_service: MistralAgentsService,
    db: AsyncSession,
    user_language: str = "de",
    user_message_id: UUID | None = None,
    user: User | None = None,
    cancel_event: asyncio.Event | None = None,
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
        user_message_id: UUID of the user message that triggered this processing
    """
    try:
        # Initialize Mistral client with optimized timeout settings
        client = get_mistral_async_client()

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

        # Track current agent for database updates (persisted from last handoff)
        current_agent_name = conversation.current_agent or "router"
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

        # NOTE: Per-request `instructions` param on start_stream is mutually exclusive with `agent_id`.
        # Safety guardrails are baked into agent prompts via SUMII_CORE_DOS_DONTS instead.

        # Inject user profile context on the first message of a new conversation.
        # This gets stored in Mistral's server-side history so all agents
        # (including Summary Agent) can reference the user's profile data.
        if not conversation.mistral_conversation_id and user:
            profile_context = build_user_profile_context(user)
            if profile_context:
                user_message_content = profile_context + user_message_content
                logger.info("[PROFILE] Injected user profile context into first message")

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

        # Create ThinkingSteps in database and persist first step
        thinking_steps = await get_or_create_thinking_steps(
            db, conversation.id, current_agent_name, thinking_title, user_message_id
        )

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
                    # Inject user profile since this is a fresh conversation
                    retry_content = user_message_content
                    if user:
                        profile_context = build_user_profile_context(user)
                        if profile_context:
                            retry_content = profile_context + user_message_content
                            logger.info("[PROFILE] Injected user profile into retry start_stream")
                    logger.info(f"🔄 [MISTRAL] Retrying with start_stream() for router_id={router_id}")
                    response = client.beta.conversations.start_stream(
                        agent_id=router_id,
                        inputs=retry_content,
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
        # Track function calls - only post-handoff calls get sent back to Mistral
        pending_function_calls: list[dict] = []  # Each: {tool_call_id, function_name, arguments}
        pre_handoff_calls: list[dict] = []  # Function calls from BEFORE the last handoff (execute locally only)
        current_function_call: dict | None = None  # Currently accumulating function call
        event_count = 0  # Track for progress logging

        logger.info("📡 [STREAM] Starting stream processing...")

        # Stream state for thinking_preview: accumulates text per-agent, resets on handoff
        stream_state: dict = {"text_accumulator": "", "chunk_counter": 0}

        with response as event_stream:
            # CRITICAL: ALL next() calls use executor + timeout to prevent blocking the event loop.
            # Mistral can return HTTP 200 but stall before sending the first SSE event.
            stream_iter = iter(event_stream)
            executor = ThreadPoolExecutor(max_workers=1)
            loop = asyncio.get_event_loop()

            def _next_event():
                try:
                    return next(stream_iter), False
                except StopIteration:
                    return None, True

            # Get first event with timeout (captures conversation_id)
            try:
                first_result_raw = await asyncio.wait_for(
                    loop.run_in_executor(executor, _next_event),
                    timeout=90.0,
                )
                first_event, first_exhausted = first_result_raw
            except asyncio.TimeoutError:
                logger.error("⚠️ [TIMEOUT] First stream event timed out after 90s — Mistral stream stalled")
                first_event, first_exhausted = None, True

            # Handle timeout OR empty stream — check server-side history for completed response
            if first_event is None or first_exhausted:
                logger.warning("⚠️ [STREAM] No events received — checking server-side history")
                recovered = await _recover_from_stream_timeout(client, conversation)
                if recovered:
                    recovered = sanitize_agent_text(recovered)
                    logger.info(f"✅ [RECOVERY] Delivering recovered response ({len(recovered)} chars)")
                    await websocket.send_json(
                        {"type": "message_chunk", "content": recovered, "agent": current_agent_name}
                    )
                    # Save recovered response as AI message
                    ai_message = Message(
                        conversation_id=conversation.id,
                        role=MessageRole.ASSISTANT,
                        content=recovered,
                        agent_name=current_agent_name,
                    )
                    db.add(ai_message)
                    await db.commit()
                    await db.refresh(ai_message)
                    await websocket.send_json(
                        {
                            "type": "message_complete",
                            "message_id": str(ai_message.id),
                            "content": recovered,
                            "agent": current_agent_name,
                            "timestamp": ai_message.created_at.isoformat(),
                        }
                    )
                    # Finalize thinking steps
                    if thinking_steps:
                        await complete_agent_step(db, thinking_steps, current_agent_name)
                        thinking_steps.is_live = False
                        thinking_steps.completed_at = datetime.now(timezone.utc)
                        db.add(thinking_steps)
                        await db.commit()
                    conversation.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                else:
                    # Could not recover — keep conversation_id intact for retry
                    logger.warning("[RECOVERY] Keeping mistral_conversation_id intact for retry")
                    await websocket.send_json({"type": "error", "message": "Response timed out. Please try again."})
                return

            logger.info("⚡ [TRACE] Got first event from stream")

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
                thinking_steps,
                user_language,
                stream_state,
            )
            if isinstance(first_result, tuple) and first_result[0] == "function_call":
                current_function_call = {
                    "tool_call_id": first_result[1],
                    "function_name": first_result[2],
                    "arguments": first_result[3] or "",
                }

            # Process remaining events using async-safe iteration
            stream_done = False

            async def get_next_event() -> tuple[Any | None, bool, bool]:
                """Get next event from stream in executor with timeout.
                Returns (event, exhausted, timed_out).
                Reuses executor, loop, and _next_event defined above."""
                try:
                    event, exhausted = await asyncio.wait_for(
                        loop.run_in_executor(executor, _next_event),
                        timeout=90.0,  # 90s timeout per event (increased for Magistral thinking)
                    )
                    return event, exhausted, False
                except asyncio.TimeoutError:
                    return None, False, True

            cancelled = False

            while not stream_done:
                # Check for user-initiated cancellation before fetching next event
                if cancel_event and cancel_event.is_set():
                    logger.info("[CANCEL] Generation cancelled by user")
                    cancelled = True
                    break

                event, exhausted, timed_out = await get_next_event()

                if exhausted:
                    logger.info("🔵 [TRACE] Stream iterator exhausted (StopIteration)")
                    break

                if timed_out:
                    logger.warning("⚠️ [TIMEOUT] Stream next() timed out after 90s")
                    # Keep conversation_id intact — check history for any completed content we missed
                    recovered = await _recover_from_stream_timeout(client, conversation)
                    if recovered:
                        recovered = sanitize_agent_text(recovered)
                        # Only add content we haven't already received
                        existing_text = "".join(full_response_parts)
                        if len(recovered) > len(existing_text):
                            extra = recovered[len(existing_text) :]
                            full_response_parts.append(extra)
                            await websocket.send_json(
                                {"type": "message_chunk", "content": extra, "agent": current_agent_name}
                            )
                    else:
                        logger.warning("[RECOVERY] Keeping mistral_conversation_id intact for retry")
                    break

                if event is None:
                    break

                logger.info(f"⚡ [TRACE] Got event #{event_count + 1} from stream")
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
                    thinking_steps,
                    user_language,
                    stream_state,
                )
                logger.debug(f"🔴 [TRACE] _process_single_event returned: {result}")

                # Check result IMMEDIATELY after processing - before trying to get next event
                if result == "done":
                    logger.info(f"✅ [STREAM] Stream complete after {event_count} events")
                    logger.info("🔵 [DEBUG] Got result='done', breaking NOW (before next iteration)")
                    stream_done = True
                    # Continue to process any pending function call before breaking
                elif result == "handoff":
                    # Update current agent from handoff
                    current_agent_name = getattr(event.data, "next_agent_name", current_agent_name)
                    current_agent_name = current_agent_name.lower().replace(" ", "_").replace("legal_", "")
                    # CRITICAL: Move pre-handoff function calls aside.
                    # After a handoff, Mistral only expects results for the NEW agent's calls.
                    # Pre-handoff calls still get executed locally (side effects) but must NOT
                    # be sent back via append_stream — that causes error 3230.
                    if current_function_call:
                        pending_function_calls.append(current_function_call)
                        current_function_call = None
                    if pending_function_calls:
                        logger.info(
                            f"🔄 [HANDOFF] Moving {len(pending_function_calls)} pre-handoff function call(s) "
                            f"to local-only execution"
                        )
                        pre_handoff_calls.extend(pending_function_calls)
                        pending_function_calls = []
                elif result == "error":
                    logger.error(f"❌ [STREAM] Error after {event_count} events")
                    # Finalize ThinkingSteps so it doesn't stay is_live=True forever
                    if thinking_steps:
                        thinking_steps.is_live = False
                        thinking_steps.completed_at = datetime.now(timezone.utc)
                        db.add(thinking_steps)
                        await db.commit()
                    await websocket.send_json(
                        {
                            "type": "thinking_complete",
                            "data": {"error": True},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
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

        logger.info("🔵 [DEBUG] Exited the with block (stream closed)")
        logger.info(
            f"📡 [STREAM] Stream ended. Total events: {event_count}, "
            f"Functions pending: {len(pending_function_calls)}, "
            f"Pre-handoff (local-only): {len(pre_handoff_calls)}"
        )

        # Handle cancellation — save partial response, finalize ThinkingSteps, return early
        if cancelled:
            partial_text = "".join(full_response_parts)
            logger.info(f"[CANCEL] Saving partial response ({len(partial_text)} chars)")

            # Save partial response as Message (valuable context for future messages)
            partial_message_id: str | None = None
            if partial_text:
                ai_message = Message(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=partial_text,
                    agent_name=current_agent_name,
                )
                db.add(ai_message)
                await db.commit()
                await db.refresh(ai_message)
                partial_message_id = str(ai_message.id)

            # Finalize ThinkingSteps so they don't stay is_live=True forever
            if thinking_steps:
                # Persist preview_text for the current agent before finalizing
                preview = stream_state["text_accumulator"][-120:] if stream_state.get("text_accumulator") else None
                await complete_agent_step(db, thinking_steps, current_agent_name, preview_text=preview)
                thinking_steps.is_live = False
                thinking_steps.completed_at = datetime.now(timezone.utc)
                db.add(thinking_steps)
                await db.commit()

            # Notify client of cancellation
            try:
                await websocket.send_json(
                    {
                        "type": "generation_cancelled",
                        "partial_text": partial_text,
                        "message_id": partial_message_id,
                        "agent": current_agent_name,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception:
                pass  # WS may be closed

            # Update conversation metadata
            conversation.current_agent = current_agent_name
            conversation.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return  # Skip function processing and summary trigger

        # Process ALL function calls for side effects (WS events, DB updates, etc.)
        # But ONLY send post-handoff function results back to Mistral.
        # Pre-handoff calls were from a previous agent — Mistral doesn't expect results for them
        # after a handoff (error 3230: "Not the same number of function calls and responses").
        trigger_summary_generation = False
        summary_case_data = None

        function_results: list[FunctionResultEntry] = []
        # Merge both lists for local processing; track which IDs to send to Mistral
        all_function_calls = pre_handoff_calls + pending_function_calls
        post_handoff_ids = {fc["tool_call_id"] for fc in pending_function_calls}

        if all_function_calls:
            logger.info(f"{'='*40}")
            logger.info(
                f"🔧 [FUNC] Processing {len(all_function_calls)} function call(s) "
                f"({len(pre_handoff_calls)} local-only, {len(pending_function_calls)} to send)..."
            )
            logger.info(f"{'='*40}")

        for func_call in all_function_calls:
            tool_call_id = func_call["tool_call_id"]
            fn_name = func_call["function_name"]
            arguments = func_call["arguments"]
            is_post_handoff = tool_call_id in post_handoff_ids

            logger.info(
                f"🔧 [FUNC] Processing: {fn_name} (id: {tool_call_id})"
                f"{'' if is_post_handoff else ' [LOCAL-ONLY, pre-handoff]'}"
            )

            result_entry, case_data, should_trigger = await _handle_function_call(
                fn_name, arguments, tool_call_id, conversation, websocket, user, logger
            )

            if should_trigger:
                trigger_summary_generation = True
                summary_case_data = case_data

            # Only send function results for post-handoff calls
            # Pre-handoff calls were executed locally but Mistral doesn't expect their results
            if is_post_handoff:
                function_results.append(result_entry)
                logger.info(f"🔵 [DEBUG] Added result for {fn_name}, total: {len(function_results)}")
            else:
                logger.info(f"🔵 [DEBUG] Skipping Mistral result for pre-handoff call: {fn_name}")

        # Send function results back to Mistral and process continuation streams.
        # CRITICAL: This is a LOOP — continuation streams can produce MORE function calls
        # (e.g. wrap-up calls check_completeness → track_documents → text → signal_confirmation → handoff).
        # Each round sends results back, gets a new continuation, and repeats until no more calls.
        max_continuation_depth = 5
        continuation_depth = 0
        continuation = None

        if function_results:
            func_ids = [fr.tool_call_id for fr in function_results]
            logger.info(f"📤 [FUNC] Sending {len(function_results)} result(s) back to Mistral: {func_ids}")

            conv_id = conversation.mistral_conversation_id
            if conv_id:
                try:
                    continuation = client.beta.conversations.append_stream(
                        conversation_id=conv_id,
                        inputs=function_results,
                    )
                    logger.info("[FUNC] ✅ append_stream succeeded")
                except Exception as e:
                    logger.error(f"❌ [MISTRAL] append FAILED: {e}")
                    if "404" in str(e) or "not found" in str(e).lower() or "does not have a version" in str(e).lower():
                        logger.warning(f"⚠️ [MISTRAL] Conversation {conv_id} is stale/invalid. Clearing ID.")
                        conversation.mistral_conversation_id = None
                        await db.commit()
                        continuation = None
                    else:
                        raise

        # Continuation loop — keeps chaining function call results back to Mistral
        while continuation and continuation_depth < max_continuation_depth:
            continuation_depth += 1
            logger.info(f"🔄 [CONT] Starting continuation depth={continuation_depth}")

            cont_function_call: dict | None = None
            cont_pending_calls: list[dict] = []

            with continuation as cont_stream:
                for cont_event in cont_stream:
                    cont_result = await _process_single_event(
                        cont_event,
                        websocket,
                        full_response_parts,
                        current_agent_name,
                        conversation,
                        db,
                        thinking_steps,
                        user_language,
                        stream_state,
                    )
                    if cont_result == "handoff":
                        current_agent_name = getattr(cont_event.data, "next_agent_name", current_agent_name)
                        current_agent_name = current_agent_name.lower().replace(" ", "_").replace("legal_", "")
                    elif cont_result == "done":
                        break
                    elif cont_result == "error":
                        logger.error(f"❌ [CONT] Error at depth={continuation_depth}")
                        if thinking_steps:
                            preview = (
                                stream_state["text_accumulator"][-120:]
                                if stream_state.get("text_accumulator")
                                else None
                            )
                            await complete_agent_step(db, thinking_steps, current_agent_name, preview_text=preview)
                            thinking_steps.is_live = False
                            thinking_steps.completed_at = datetime.now(timezone.utc)
                            db.add(thinking_steps)
                            await db.commit()
                        await websocket.send_json(
                            {
                                "type": "thinking_complete",
                                "data": {"error": True},
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        return
                    elif isinstance(cont_result, tuple) and cont_result[0] == "function_call":
                        new_tool_call_id = cont_result[1]
                        new_function_name = cont_result[2]
                        new_arguments = cont_result[3] or ""

                        if cont_function_call is None:
                            cont_function_call = {
                                "tool_call_id": new_tool_call_id,
                                "function_name": new_function_name,
                                "arguments": new_arguments,
                            }
                        elif cont_function_call["tool_call_id"] == new_tool_call_id:
                            cont_function_call["arguments"] += new_arguments
                        else:
                            cont_pending_calls.append(cont_function_call)
                            cont_function_call = {
                                "tool_call_id": new_tool_call_id,
                                "function_name": new_function_name,
                                "arguments": new_arguments,
                            }

            # Flush last accumulated function call
            if cont_function_call:
                cont_pending_calls.append(cont_function_call)

            if not cont_pending_calls:
                logger.info(f"🔄 [CONT] No function calls at depth={continuation_depth}, done")
                continuation = None
                break

            # Process ALL continuation function calls via the shared helper
            logger.info(
                f"🔧 [CONT] Processing {len(cont_pending_calls)} function call(s) at depth={continuation_depth}"
            )
            cont_results: list[FunctionResultEntry] = []
            for fc in cont_pending_calls:
                logger.info(f"🔧 [CONT] Processing: {fc['function_name']} (depth={continuation_depth})")
                result_entry, case_data, should_trigger = await _handle_function_call(
                    fc["function_name"],
                    fc["arguments"],
                    fc["tool_call_id"],
                    conversation,
                    websocket,
                    user,
                    logger,
                )
                if should_trigger:
                    trigger_summary_generation = True
                    summary_case_data = case_data
                # generate_summary is terminal — no result to send back
                if not should_trigger:
                    cont_results.append(result_entry)

            # Send results back to Mistral for next continuation round
            if cont_results and conversation.mistral_conversation_id:
                try:
                    continuation = client.beta.conversations.append_stream(
                        conversation_id=conversation.mistral_conversation_id,
                        inputs=cont_results,
                    )
                    logger.info(f"📤 [CONT] Sent {len(cont_results)} result(s), depth={continuation_depth}")
                except Exception as e:
                    logger.error(f"❌ [CONT] append_stream depth={continuation_depth}: {e}")
                    if "404" in str(e) or "not found" in str(e).lower() or "does not have a version" in str(e).lower():
                        conversation.mistral_conversation_id = None
                        await db.commit()
                    continuation = None
            else:
                continuation = None

        if continuation_depth >= max_continuation_depth:
            logger.warning(f"⚠️ [CONT] Hit max continuation depth ({max_continuation_depth})")

        # Combine response chunks and do a final sanitization pass
        # (catches agent names split across streaming chunks)
        full_response = sanitize_agent_text("".join(full_response_parts))

        # Finalize ThinkingSteps BEFORE message_complete so the mobile app
        # dismisses the ThinkingBubble before showing the chat bubble.
        if thinking_steps:
            preview = stream_state["text_accumulator"][-120:] if stream_state.get("text_accumulator") else None
            await complete_agent_step(db, thinking_steps, current_agent_name, preview_text=preview)
            thinking_steps.is_live = False
            thinking_steps.completed_at = datetime.now(timezone.utc)
            db.add(thinking_steps)
            await db.commit()

            await websocket.send_json(
                {
                    "type": "thinking_complete",
                    "data": {"error": False},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

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

        # AUTO-GENERATE SUMMARY if trigger was set — runs as background task
        if trigger_summary_generation and summary_case_data:
            # Send immediate "generating" event to client (if WS is still open)
            try:
                await websocket.send_json(
                    {
                        "type": "summary_generating",
                        "conversationId": str(conversation.id),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception:
                pass  # WS may already be closed, that's fine

            # Fire-and-forget background task — survives WS disconnection
            asyncio.create_task(
                _generate_summary_background(
                    conversation_id=conversation.id,
                    user_id=conversation.user_id,
                    summary_case_data=summary_case_data,
                    user_language=user_language,
                    thinking_steps_id=thinking_steps.id if thinking_steps else None,
                    websocket=websocket,
                )
            )

    except Exception as e:
        # Handle errors gracefully
        import traceback

        logger.error(f"❌ [PROCESS_ERROR] Exception in process_with_agents: {type(e).__name__}: {e}")
        logger.error(
            f"[PROCESS_ERROR] Conversation: {conversation.id}, Mistral conv: {conversation.mistral_conversation_id}"
        )
        logger.debug(f"[PROCESS_ERROR] Traceback:\n{traceback.format_exc()}")

        # Finalize ThinkingSteps so it doesn't stay is_live=True forever on error
        if thinking_steps:
            try:
                # Persist preview_text for the current agent before finalizing
                preview = stream_state["text_accumulator"][-120:] if stream_state.get("text_accumulator") else None
                await complete_agent_step(db, thinking_steps, current_agent_name, preview_text=preview)
                thinking_steps.is_live = False
                thinking_steps.completed_at = datetime.now(timezone.utc)
                db.add(thinking_steps)
                await db.commit()
            except Exception as ts_err:
                logger.error(f"[PROCESS_ERROR] Failed to finalize ThinkingSteps: {ts_err}")

        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": str(e),
                    "code": "agent_processing_error",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception:
            pass  # WS may already be closed (e.g., network loss during streaming)


async def _handle_resume(
    websocket: WebSocket,
    conversation: Conversation,
    db: AsyncSession,
    data: dict,
) -> None:
    """Handle resume request from mobile app after WebSocket reconnection.

    Validates Mistral conversation state, sends missed ThinkingSteps,
    and checks if summary was generated while user was away.
    """
    logger.info(f"[RESUME] Resume request for conversation {conversation.id}")

    # 1. Validate Mistral conversation is still alive
    current_agent = conversation.current_agent
    if conversation.mistral_conversation_id:
        try:
            client = get_mistral_async_client()
            conv_state = await client.beta.conversations.get_async(conversation_id=conversation.mistral_conversation_id)
            current_agent = getattr(conv_state, "current_agent_name", None) or conversation.current_agent
            logger.info(f"[RESUME] Mistral conversation alive, current agent: {current_agent}")
        except Exception as e:
            logger.warning(f"[RESUME] Mistral conversation expired: {e}")
            await websocket.send_json(
                {
                    "type": "conversation_expired",
                    "conversationId": str(conversation.id),
                    "reason": str(e),
                }
            )
            # Clear the stale Mistral conversation ID — next message creates fresh
            conversation.mistral_conversation_id = None
            await db.commit()
            return

    # 2. Send missed ThinkingSteps
    thinking_steps_result = await db.execute(
        select(ThinkingSteps)
        .where(ThinkingSteps.conversation_id == conversation.id)
        .order_by(ThinkingSteps.created_at.desc())
        .limit(5)
    )
    recent_steps = thinking_steps_result.scalars().all()

    steps_data = []
    for ts in recent_steps:
        steps_data.append(
            {
                "id": str(ts.id),
                "messageId": str(ts.message_id) if ts.message_id else None,
                "currentAgent": ts.current_agent,
                "completedAgents": ts.completed_agents or [],
                "steps": ts.steps or [],
                "isGeneratingSummary": ts.is_generating_summary,
                "isLive": ts.is_live,
                "createdAt": ts.created_at.isoformat() if ts.created_at else None,
                "completedAt": ts.completed_at.isoformat() if ts.completed_at else None,
            }
        )

    # 3. Check if summary was generated while user was away
    from app.models import Summary

    summary_result = await db.execute(select(Summary).where(Summary.conversation_id == conversation.id))
    summary = summary_result.scalar_one_or_none()

    # 4. Send resume_ok
    await websocket.send_json(
        {
            "type": "resume_ok",
            "conversationId": str(conversation.id),
            "currentAgent": current_agent,
            "isStreaming": False,
            "thinkingSteps": steps_data,
            "summaryReady": summary is not None,
            "summaryId": str(summary.id) if summary else None,
        }
    )
    logger.info(f"[RESUME] Sent resume_ok for conversation {conversation.id}")


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

            # Dispatch by message type
            msg_type = data.get("type")

            if msg_type == "resume":
                await _handle_resume(websocket, conversation, db, data)
                continue
            elif msg_type == "going_background":
                logger.info(f"[WS] Client going background for conversation {conversation.id}")
                continue
            elif msg_type != "message":
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

            # Refresh user's language preference (may have changed mid-session)
            await db.refresh(user, attribute_names=["language"])

            # Run process_with_agents with a concurrent cancel listener
            # so the user can send cancel_generation while processing is ongoing
            cancel_event = asyncio.Event()

            async def _listen_for_cancel() -> None:
                """Listen for cancel messages while processing."""
                try:
                    while True:
                        cancel_data = await websocket.receive_json()
                        cancel_msg_type = cancel_data.get("type")
                        if cancel_msg_type == "cancel_generation":
                            logger.info(f"[WS] Cancel requested for conversation {conversation.id}")
                            cancel_event.set()
                            return
                        elif cancel_msg_type == "going_background":
                            logger.info("[WS] Client going background during processing")
                except WebSocketDisconnect:
                    cancel_event.set()
                except Exception:
                    pass

            cancel_listener = asyncio.create_task(_listen_for_cancel())
            try:
                await process_with_agents(
                    websocket=websocket,
                    conversation=conversation,
                    user_message_content=augmented_content,
                    agents_service=agents_service,
                    db=db,
                    user_language=user.language or "de",
                    user_message_id=user_message.id,
                    user=user,
                    cancel_event=cancel_event,
                )
            finally:
                cancel_listener.cancel()
                try:
                    await cancel_listener
                except asyncio.CancelledError:
                    pass

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
