"""ThinkingBlock Model - Track agent thinking progress

ThinkingBlocks represent the AI agent processing stages shown to users.
They are created during conversations and persisted for cross-device sync.
"""

from uuid import uuid4

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class ThinkingBlock(Base):
    """Thinking block - UI state for agent progress visualization

    Attributes:
        id: Unique thinking block identifier (UUID)
        conversation_id: Foreign key to Conversation
        current_agent: Current active agent (router/intake/reasoning/wrapup/summary)
        completed_agents: List of agents that have finished
        is_generating_summary: True when summary agent is active
        is_live: True while processing, False when complete
        created_at: When thinking block was created
        completed_at: When thinking block finished (isLive became False)
    """

    __tablename__ = "thinking_blocks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

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
    conversation = relationship("Conversation", back_populates="thinking_blocks")

    # Indexes
    __table_args__ = (
        Index("ix_thinking_blocks_conversation", "conversation_id"),
        Index("ix_thinking_blocks_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ThinkingBlock(id={self.id}, conversation_id={self.conversation_id}, is_live={self.is_live})>"
