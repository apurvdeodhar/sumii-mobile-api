"""Message Model - Store individual messages in conversations

Messages represent individual chat messages between user and AI agents.
Each message belongs to a conversation and tracks which agent responded.
"""

from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.database import Base


class MessageRole(str, PyEnum):
    """Message role (who sent the message)"""

    USER = "user"  # Message from user
    ASSISTANT = "assistant"  # Message from AI agent
    SYSTEM = "system"  # System message (e.g., "Conversation started")


class Message(Base):
    """Message model - individual chat message in conversation

    Attributes:
        id: Unique message identifier (UUID)
        conversation_id: Foreign key to Conversation this message belongs to
        role: Who sent the message (user/assistant/system)
        content: Message text content
        agent_name: Which agent sent this message (null if role=user)
        function_call: JSON data for function calls (null if no function call)
        created_at: When message was created
    """

    __tablename__ = "messages"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Message data
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)  # Message text (can be long)

    # Agent metadata (only for assistant messages)
    agent_name = Column(
        String(50), nullable=True
    )  # Which agent: "router", "intake", "reasoning", "summary", null for user

    # Function calling data (JSON)
    function_call = Column(
        JSON, nullable=True
    )  # {"name": "extract_facts", "arguments": {...}} or null if no function call

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    # Indexes (composite index for efficient message retrieval)
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),  # Get messages chronologically
    )

    def __repr__(self) -> str:
        return (
            f"<Message(id={self.id}, conversation_id={self.conversation_id}, "
            f"role={self.role}, agent={self.agent_name})>"
        )
