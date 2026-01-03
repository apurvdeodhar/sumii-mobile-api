"""Conversation Pydantic Schemas - Request/Response models for conversations API"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import CaseStrength, ConversationStatus, LegalArea, Urgency


# Conversation Create (POST request)
class ConversationCreate(BaseModel):
    """Create conversation request schema

    Only title is optional - everything else is set by agents during conversation
    """

    title: str | None = Field(None, max_length=200, description="Optional conversation title")


# Conversation Update (PATCH request)
class ConversationUpdate(BaseModel):
    """Update conversation request schema

    All fields optional - only provided fields will be updated
    """

    title: str | None = Field(None, max_length=200)
    status: ConversationStatus | None = None
    legal_area: LegalArea | None = None
    case_strength: CaseStrength | None = None
    urgency: Urgency | None = None


# Conversation Response (GET response)
class ConversationResponse(BaseModel):
    """Conversation response schema (without messages)

    Used for listing conversations (GET /conversations)
    """

    id: UUID
    user_id: UUID
    title: str | None
    status: ConversationStatus
    legal_area: LegalArea | None
    case_strength: CaseStrength | None
    urgency: Urgency | None
    current_agent: str | None
    created_at: datetime
    updated_at: datetime
    # Wrap-up confirmation fields
    wrapup_confirmed: bool = False
    wrapup_content: str | None = None
    wrapup_confirmed_at: datetime | None = None

    model_config = {"from_attributes": True}


# Message Response (nested in conversation)
class MessageResponse(BaseModel):
    """Message response schema (nested in ConversationWithMessages)"""

    id: UUID
    conversation_id: UUID
    role: str
    content: str
    agent_name: str | None
    function_call: dict[str, Any] | None
    document_ids: list[UUID] | None = None  # Attached document UUIDs
    created_at: datetime

    model_config = {"from_attributes": True}


# Conversation with Messages (GET /conversations/{id})
class ConversationWithMessages(ConversationResponse):
    """Full conversation with all messages

    Used for retrieving single conversation (GET /conversations/{id})
    """

    messages: list[MessageResponse] = []

    # Include dynamic orchestration metadata for debugging/admin
    facts_collected: dict[str, Any] | None = None
    analysis_done: bool = False
    summary_generated: bool = False

    # 5W framework facts
    who: dict[str, Any] | None = None
    what: dict[str, Any] | None = None
    when: dict[str, Any] | None = None
    where: dict[str, Any] | None = None
    why: dict[str, Any] | None = None

    model_config = {"from_attributes": True}
