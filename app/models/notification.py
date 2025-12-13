"""Notification Model - Store user notifications

Notifications are created for various events:
- Summary ready
- Lawyer response
- New message (if user not active)
- Case updates
"""

import uuid
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class NotificationType(str, Enum):
    """Notification types"""

    NEW_MESSAGE = "new_message"  # New message in conversation
    SUMMARY_READY = "summary_ready"  # Summary generated for conversation
    LAWYER_RESPONSE = "lawyer_response"  # Lawyer responded to case
    LAWYER_ASSIGNED = "lawyer_assigned"  # Lawyer accepted case
    CASE_UPDATED = "case_updated"  # Case status changed


class Notification(Base):
    """Notification model - user notifications for events

    Attributes:
        id: Unique notification identifier (UUID)
        user_id: Foreign key to User who receives this notification
        type: Notification type (enum)
        title: Notification title (e.g., "Zusammenfassung bereit")
        message: Notification message (e.g., "Ihre Rechtsübersicht ist verfügbar")
        data: Extra data in JSONB (conversation_id, summary_id, lawyer_id, etc.)
        read: Whether notification has been read (default: False)
        created_at: When notification was created
    """

    __tablename__ = "notifications"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Notification content
    type = Column(String(50), nullable=False, index=True)  # NotificationType enum value
    title = Column(String(200), nullable=False)  # Notification title
    message = Column(Text, nullable=False)  # Notification message
    data = Column(JSONB, nullable=True)  # Extra data: {"conversation_id": "...", "summary_id": "...", etc.}

    # Read status
    read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)  # When notification was read (for analytics)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actioned_at = Column(DateTime(timezone=True), nullable=True)  # When user clicked/actioned notification

    # Indexes (composite indexes for common queries)
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),  # Get unread notifications for user
        Index("ix_notifications_user_created", "user_id", "created_at"),  # List user's notifications by date
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type}, read={self.read})>"
