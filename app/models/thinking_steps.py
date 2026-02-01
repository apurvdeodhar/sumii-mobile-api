"""ThinkingSteps Model - Track agent thinking progress

ThinkingSteps represent the AI agent processing stages shown to users.
They are created during conversations and persisted for cross-device sync.
"""

from uuid import uuid4

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class ThinkingSteps(Base):
    """Thinking steps - UI state for agent progress visualization

    Attributes:
        id: Unique thinking steps identifier (UUID)
        conversation_id: Foreign key to Conversation
        current_agent: Current active agent (router/intake/reasoning/wrapup/summary)
        completed_agents: List of agents that have finished
        is_generating_summary: True when summary agent is active
        is_live: True while processing, False when complete
        created_at: When thinking steps was created
        completed_at: When thinking steps finished (isLive became False)
    """

    __tablename__ = "thinking_steps"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Link to the user message that triggered this thinking steps
    # Enables per-message ThinkingBubble rendering in UI
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True)

    # Agent progress state
    current_agent = Column(String(50), nullable=True)
    completed_agents = Column(JSONB, default=list, nullable=False)
    # Progressive agent steps with titles: [{agentId, title, status, timestamp}]
    steps = Column(JSONB, default=list, nullable=False)
    is_generating_summary = Column(Boolean, default=False, nullable=False)
    is_live = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="thinking_steps")

    # Indexes
    __table_args__ = (
        Index("ix_thinking_steps_conversation", "conversation_id"),
        Index("ix_thinking_steps_message", "message_id"),
        Index("ix_thinking_steps_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ThinkingSteps(id={self.id}, conversation_id={self.conversation_id}, is_live={self.is_live})>"
