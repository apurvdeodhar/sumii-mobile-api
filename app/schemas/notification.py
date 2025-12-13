"""Notification Schemas - Request/Response models for notifications API"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    """Notification response schema"""

    id: UUID
    user_id: UUID
    type: NotificationType
    title: str
    message: str
    data: dict[str, Any] | None = None  # Extra data: conversation_id, summary_id, lawyer_id, etc.
    read: bool
    read_at: datetime | None = None
    created_at: datetime
    actioned_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """List of notifications with pagination"""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int


class NotificationMarkRead(BaseModel):
    """Mark notification as read request schema"""

    read: bool = Field(True, description="Mark as read (always true for this endpoint)")


class NotificationUnreadCountResponse(BaseModel):
    """Unread notification count response"""

    unread_count: int
