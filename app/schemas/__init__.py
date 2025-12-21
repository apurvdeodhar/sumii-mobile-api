"""Pydantic Schemas"""

from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessages,
    MessageResponse,
)
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUpload
from app.schemas.lawyer_connection import (
    LawyerConnectionCreate,
    LawyerConnectionListResponse,
    LawyerConnectionResponse,
    LawyerSearchParams,
)
from app.schemas.notification import (
    NotificationListResponse,
    NotificationMarkRead,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from app.schemas.push import PushTokenRegister, PushTokenRegisterResponse
from app.schemas.sse import (
    CaseUpdatedEvent,
    LawyerAssignedEvent,
    LawyerResponseEvent,
    SSEEvent,
    SSEEventBase,
    SummaryReadyEvent,
)
from app.schemas.summary import SummaryCreate, SummaryResponse
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.websocket import (
    AgentHandoffDoneEvent,
    AgentHandoffEvent,
    AgentHandoffStartedEvent,
    AgentStartEvent,
    ErrorEvent,
    FunctionCallEvent,
    MessageChunkEvent,
    MessageCompleteEvent,
    WebSocketEvent,
    WebSocketEventBase,
    WebSocketMessageRequest,
)

__all__ = [
    # User schemas
    "UserCreate",
    "UserRead",
    "UserUpdate",
    # Conversation schemas
    "ConversationCreate",
    "ConversationUpdate",
    "ConversationResponse",
    "ConversationWithMessages",
    "MessageResponse",
    # Document schemas
    "DocumentUpload",
    "DocumentResponse",
    "DocumentListResponse",
    # Summary schemas
    "SummaryCreate",
    "SummaryResponse",
    # Notification schemas
    "NotificationResponse",
    "NotificationListResponse",
    "NotificationMarkRead",
    "NotificationUnreadCountResponse",
    # Lawyer connection schemas
    "LawyerConnectionCreate",
    "LawyerConnectionResponse",
    "LawyerConnectionListResponse",
    "LawyerSearchParams",
    # WebSocket event schemas
    "WebSocketMessageRequest",
    "WebSocketEventBase",
    "AgentStartEvent",
    "MessageChunkEvent",
    "MessageCompleteEvent",
    "AgentHandoffStartedEvent",
    "AgentHandoffDoneEvent",
    "AgentHandoffEvent",
    "FunctionCallEvent",
    "ErrorEvent",
    "WebSocketEvent",
    # SSE event schemas
    "SSEEventBase",
    "SummaryReadyEvent",
    "LawyerResponseEvent",
    "LawyerAssignedEvent",
    "CaseUpdatedEvent",
    "SSEEvent",
    # Push notification schemas
    "PushTokenRegister",
    "PushTokenRegisterResponse",
]
