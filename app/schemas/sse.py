"""SSE Event Schemas - Request/Response models for SSE (Server-Sent Events) API"""

from typing import Any

from pydantic import BaseModel


# SSE Events (for notifications, not chat)
class SSEEventBase(BaseModel):
    """Base class for all SSE events"""

    type: str
    title: str
    message: str
    data: dict[str, Any] | None = None  # Extra data: conversation_id, summary_id, etc.


class SummaryReadyEvent(SSEEventBase):
    """Summary ready event"""

    type: str = "summary_ready"
    title: str = "Zusammenfassung bereit"
    message: str = "Ihre Rechtsübersicht ist verfügbar"
    data: dict[str, Any]  # {"conversation_id": "uuid", "summary_id": "uuid"}


class LawyerResponseEvent(SSEEventBase):
    """Lawyer response event"""

    type: str = "lawyer_response"
    title: str = "Anwalt hat geantwortet"
    message: str = "Ihr Anwalt hat auf Ihren Fall geantwortet"
    data: dict[str, Any]  # {"conversation_id": "uuid", "lawyer_name": "Dr. Schmidt"}


class LawyerAssignedEvent(SSEEventBase):
    """Lawyer assigned event"""

    type: str = "lawyer_assigned"
    title: str = "Anwalt zugewiesen"
    message: str = "Ein Anwalt wurde Ihrem Fall zugewiesen"
    data: dict[str, Any]  # {"conversation_id": "uuid", "lawyer_id": 123, "lawyer_name": "Dr. Schmidt"}


class CaseUpdatedEvent(SSEEventBase):
    """Case updated event"""

    type: str = "case_updated"
    title: str = "Fall aktualisiert"
    message: str = "Ihr Fall wurde aktualisiert"
    data: dict[str, Any]  # {"conversation_id": "uuid", "status": "completed"}


# Union type for all SSE events
SSEEvent = SummaryReadyEvent | LawyerResponseEvent | LawyerAssignedEvent | CaseUpdatedEvent
