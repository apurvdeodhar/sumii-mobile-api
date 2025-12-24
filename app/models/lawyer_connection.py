"""Lawyer Connection Model - Track user connections to lawyers

Tracks when users connect their conversations/summaries to lawyers
from the sumii-anwalt directory.
"""

import uuid
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ConnectionStatus(str, Enum):
    """Lawyer connection status"""

    PENDING = "pending"  # Connection request sent, waiting for lawyer response
    ACCEPTED = "accepted"  # Lawyer accepted the case
    REJECTED = "rejected"  # Lawyer rejected the case
    CANCELLED = "cancelled"  # User cancelled the connection


class LawyerConnection(Base):
    """Lawyer connection model - tracks user connections to lawyers

    Attributes:
        id: Unique connection identifier (UUID)
        user_id: Foreign key to User who initiated connection
        conversation_id: Foreign key to Conversation (the legal case)
        summary_id: Foreign key to Summary (the legal summary sent to lawyer)
        lawyer_id: Lawyer ID from sumii-anwalt system (integer, not UUID)
        lawyer_name: Lawyer name (cached for display)
        status: Connection status (pending/accepted/rejected/cancelled)
        case_id: Case ID in sumii-anwalt system (if case was created)
        created_at: When connection was initiated
        updated_at: When connection status was last updated
    """

    __tablename__ = "lawyer_connections"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_id = Column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="SET NULL"), nullable=True, index=True
    )  # SET NULL because summary might be deleted but connection should remain

    # Lawyer information (from sumii-anwalt)
    lawyer_id = Column(Integer, nullable=False, index=True)  # Lawyer ID from sumii-anwalt (not UUID)
    lawyer_name = Column(String(200), nullable=True)  # Cached lawyer name for display

    # Connection request metadata
    user_message = Column(Text, nullable=True)  # Optional message from user when requesting connection
    rejection_reason = Column(Text, nullable=True)  # Reason if lawyer rejected (optional)

    # Connection status
    status = Column(String(50), nullable=False, default=ConnectionStatus.PENDING.value, index=True)
    status_changed_at = Column(DateTime(timezone=True), nullable=True)  # When status last changed

    # Case tracking (from sumii-anwalt)
    case_id = Column(String(100), nullable=True)  # Case ID in sumii-anwalt system (format: SUMII-XXXXXXXX)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    lawyer_response_at = Column(DateTime(timezone=True), nullable=True)  # When lawyer responded (accepted/rejected)

    # Indexes (composite indexes for common queries)
    __table_args__ = (
        Index("ix_lawyer_connections_user_status", "user_id", "status"),  # List user's connections by status
        Index("ix_lawyer_connections_conversation", "conversation_id"),  # Get connection for conversation
        Index("ix_lawyer_connections_user_created", "user_id", "created_at"),  # List user's connections by date
    )

    def __repr__(self) -> str:
        return (
            f"<LawyerConnection(id={self.id}, user_id={self.user_id}, "
            f"lawyer_id={self.lawyer_id}, status={self.status})>"
        )
