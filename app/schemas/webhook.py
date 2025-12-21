"""Webhook Schemas - Request/Response models for webhook endpoints"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LawyerResponseWebhookRequest(BaseModel):
    """Webhook request schema for lawyer response from sumii-anwalt

    This is called by sumii-anwalt backend when a lawyer responds to a case.
    """

    case_id: int = Field(..., description="Case ID in sumii-anwalt")
    conversation_id: UUID = Field(..., description="User's conversation ID")
    user_id: UUID = Field(..., description="User ID who owns the conversation")
    lawyer_id: int = Field(..., description="Lawyer ID in sumii-anwalt")
    lawyer_name: str = Field(..., description="Lawyer's full name")
    response_text: str = Field(..., description="Lawyer's response text to the user")
    response_timestamp: datetime = Field(..., description="When lawyer responded (ISO 8601)")


class LawyerResponseWebhookResponse(BaseModel):
    """Webhook response schema"""

    status: str = Field(default="success", description="Status of webhook processing")
    message: str = Field(..., description="Human-readable message")
    notification_id: UUID | None = Field(None, description="ID of created notification")
    email_sent: bool = Field(default=False, description="Whether email was sent to user")
