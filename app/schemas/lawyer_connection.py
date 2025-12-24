"""Lawyer Connection Schemas - Request/Response models for lawyer connection API"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.lawyer_connection import ConnectionStatus


class LawyerConnectionCreate(BaseModel):
    """Create lawyer connection request schema"""

    conversation_id: UUID = Field(..., description="Conversation ID to connect to lawyer")
    lawyer_id: int = Field(..., description="Lawyer ID from sumii-anwalt system")
    user_message: str | None = Field(None, max_length=1000, description="Optional message from user")


class LawyerConnectionResponse(BaseModel):
    """Lawyer connection response schema"""

    id: UUID
    user_id: UUID
    conversation_id: UUID
    summary_id: UUID | None
    lawyer_id: int
    lawyer_name: str | None
    user_message: str | None
    rejection_reason: str | None
    status: ConnectionStatus
    status_changed_at: datetime | None
    case_id: str | None  # Case ID from sumii-anwalt (format: SUMII-XXXXXXXX)
    created_at: datetime
    updated_at: datetime
    lawyer_response_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class LawyerConnectionListResponse(BaseModel):
    """List of lawyer connections"""

    connections: list[LawyerConnectionResponse]
    total: int


class LawyerSearchParams(BaseModel):
    """Lawyer search query parameters"""

    lat: float | None = Field(None, description="Latitude for location-based search")
    lng: float | None = Field(None, description="Longitude for location-based search")
    radius: int | None = Field(None, ge=1, le=100, description="Search radius in km (1-100)")
    legal_area: str | None = Field(None, description="Filter by legal area")
    language: str | None = Field(None, description="Filter by language (de, en)")
    limit: int = Field(20, ge=1, le=100, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")
