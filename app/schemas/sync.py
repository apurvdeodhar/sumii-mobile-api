"""Sync Pydantic Schemas - Request/Response models for mobile sync API"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.conversation import ConversationResponse, MessageResponse
from app.schemas.document import DocumentResponse
from app.schemas.notification import NotificationResponse
from app.schemas.summary import SummaryResponse


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


class SyncResponse(BaseModel):
    """Sync response schema - returns all changes since last_synced_at"""

    # Changed/new records
    conversations: list[ConversationResponse] = []
    messages: list[MessageResponse] = []
    documents: list[DocumentResponse] = []
    summaries: list[SummaryResponse] = []
    notifications: list[NotificationResponse] = []

    # Deleted record IDs
    deleted_ids: DeletedIds = Field(default_factory=DeletedIds)

    # Server timestamp - client saves for next sync
    server_time: datetime = Field(
        default_factory=datetime.utcnow,
        description="Server timestamp to use as last_synced_at for next sync",
    )

    # Sync metadata
    is_full_sync: bool = Field(False, description="True if this was a full sync (client had no last_synced_at)")
