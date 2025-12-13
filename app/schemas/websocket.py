"""WebSocket Event Schemas - Request/Response models for WebSocket chat API"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


# Client → Server Messages
class WebSocketMessageRequest(BaseModel):
    """WebSocket message request (client → server)"""

    type: str = "message"  # Always "message"
    content: str  # User's message text


# Server → Client Events
class WebSocketEventBase(BaseModel):
    """Base class for all WebSocket events"""

    type: str
    timestamp: str  # ISO datetime string


class AgentStartEvent(WebSocketEventBase):
    """Agent started processing event"""

    type: str = "agent_start"
    agent: str  # "router" | "intake" | "reasoning" | "summary"


class MessageChunkEvent(WebSocketEventBase):
    """Message chunk (streaming) event"""

    type: str = "message_chunk"
    content: str  # Chunk of message content
    agent: str  # Current agent name


class MessageCompleteEvent(WebSocketEventBase):
    """Message complete event"""

    type: str = "message_complete"
    message_id: UUID  # ID of completed message
    content: str  # Full message text
    agent: str  # Agent that generated the message


class AgentHandoffStartedEvent(WebSocketEventBase):
    """Agent handoff started event"""

    type: str = "agent_handoff_started"
    from_agent: str  # Previous agent name


class AgentHandoffDoneEvent(WebSocketEventBase):
    """Agent handoff completed event"""

    type: str = "agent_handoff_done"
    to_agent: str  # New agent name


class AgentHandoffEvent(WebSocketEventBase):
    """Combined agent handoff event (alternative format)"""

    type: str = "agent_handoff"
    from_agent: str  # Previous agent
    to_agent: str  # New agent
    reason: str | None = None  # Reason for handoff


class FunctionCallEvent(WebSocketEventBase):
    """Function call event"""

    type: str = "function_call"
    function: str  # Function name
    arguments: dict[str, Any]  # Function arguments


class ErrorEvent(WebSocketEventBase):
    """Error event"""

    type: str = "error"
    error: str  # Error description
    code: str | None = None  # Error code


# Union type for all WebSocket events
WebSocketEvent = (
    AgentStartEvent
    | MessageChunkEvent
    | MessageCompleteEvent
    | AgentHandoffStartedEvent
    | AgentHandoffDoneEvent
    | AgentHandoffEvent
    | FunctionCallEvent
    | ErrorEvent
)
