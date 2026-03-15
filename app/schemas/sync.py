"""Sync Pydantic Schemas - Request/Response models for mobile sync API"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.conversation import ConversationResponse, MessageResponse
from app.schemas.document import DocumentResponse
from app.schemas.lawyer_connection import LawyerConnectionResponse
from app.schemas.notification import NotificationResponse
from app.schemas.summary import SummaryResponse
from app.schemas.thinking_steps import ThinkingStepsResponse


class UserProfileSyncResponse(BaseModel):
    """User profile fields included in sync response"""

    id: str
    email: str
    nickname: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_postal_code: str | None = None
    language: str | None = None
    legal_insurance: bool | None = None
    insurance_company: str | None = None
    insurance_number: str | None = None


class SyncRequest(BaseModel):
    """Sync request schema - client sends last sync timestamp"""

    last_synced_at: datetime | None = Field(None, description="Timestamp of last successful sync. If None, full sync.")


class DeletedIds(BaseModel):
    """IDs of soft-deleted records since last sync"""

    conversations: list[UUID] = []
    messages: list[UUID] = []
    documents: list[UUID] = []
    summaries: list[UUID] = []
    notifications: list[UUID] = []
    lawyer_connections: list[UUID] = []
    thinking_steps: list[UUID] = []


class SyncResponse(BaseModel):
    """Sync response schema - returns all changes since last_synced_at"""

    # Changed/new records
    conversations: list[ConversationResponse] = []
    messages: list[MessageResponse] = []
    documents: list[DocumentResponse] = []
    summaries: list[SummaryResponse] = []
    notifications: list[NotificationResponse] = []
    lawyer_connections: list[LawyerConnectionResponse] = []
    thinking_steps: list[ThinkingStepsResponse] = []

    # User profile (always included — serves as persistent profile source of truth)
    user_profile: UserProfileSyncResponse | None = None

    # Deleted record IDs
    deleted_ids: DeletedIds = Field(default_factory=DeletedIds)

    # Server timestamp - client saves for next sync
    server_time: datetime = Field(
        default_factory=datetime.utcnow,
        description="Server timestamp to use as last_synced_at for next sync",
    )

    # Sync metadata
    is_full_sync: bool = Field(False, description="True if this was a full sync (client had no last_synced_at)")
