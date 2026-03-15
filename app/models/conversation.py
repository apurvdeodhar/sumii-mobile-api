"""Conversation Model - Store user conversations with AI agents

Conversations represent individual legal intake sessions.
Each conversation has multiple messages and tracks the current agent state.
"""

from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import UUID, Boolean, Column, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class ConversationStatus(str, PyEnum):
    """Conversation lifecycle status"""

    ACTIVE = "active"  # Ongoing conversation
    COMPLETED = "completed"  # Summary generated, conversation finished
    ARCHIVED = "archived"  # User archived (no longer active)


class LegalArea(str, PyEnum):
    """German Civil Law areas (8 domains from Nick's taxonomy + Other fallback)"""

    VERTRAGSRECHT = "Vertragsrecht"  # Contract Law
    MIETRECHT = "Mietrecht"  # Tenancy Law
    ARBEITSRECHT = "Arbeitsrecht"  # Employment Law
    FAMILIENRECHT = "Familienrecht"  # Family Law
    ERBRECHT = "Erbrecht"  # Succession / Inheritance
    DELIKTSRECHT = "Deliktsrecht"  # Tort Law (Wrongdoing)
    SACHENRECHT = "Sachenrecht"  # Property Law (Immobiliar)
    GESELLSCHAFTSRECHT = "Gesellschaftsrecht"  # Company Law
    OTHER = "Other"  # Other / unclassified


class UserIntent(str, PyEnum):
    """User intent type — dispute vs document drafting"""

    DISPUTE = "dispute"  # Concrete case / active problem
    DRAFTING = "drafting"  # Document drafting / creation


class CaseStrength(str, PyEnum):
    """Legal case strength assessment"""

    STRONG = "strong"  # Strong legal position
    MEDIUM = "medium"  # Medium legal position
    WEAK = "weak"  # Weak legal position


class Urgency(str, PyEnum):
    """Matter urgency level"""

    IMMEDIATE = "immediate"  # Urgent, needs immediate action
    WEEKS = "weeks"  # Can wait a few weeks
    MONTHS = "months"  # Not urgent, can wait months


class Conversation(Base):
    """Conversation model - user's legal intake session

    Attributes:
        id: Unique conversation identifier (UUID)
        user_id: Foreign key to User who owns this conversation
        title: Optional conversation title (e.g., "Mietrecht - Kaputte Heizung")
        status: Conversation status (active/completed/archived)
        legal_area: Area of German Civil Law (Mietrecht/Arbeitsrecht/etc.)
        case_strength: Legal case strength (strong/medium/weak)
        urgency: How urgent the matter is (immediate/weeks/months)
        current_agent: Current agent handling conversation (router/intake/reasoning/summary)
        created_at: When conversation was created
        updated_at: When conversation was last updated
    """

    __tablename__ = "conversations"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Conversation metadata
    title = Column(String(200), nullable=True)  # Optional, can be auto-generated or user-provided
    status = Column(Enum(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False, index=True)

    # Legal analysis metadata (filled by agents)
    legal_area = Column(Enum(LegalArea), nullable=True)  # Set by Router/Intake Agent
    user_intent = Column(Enum(UserIntent), nullable=True)  # Set by Router: dispute or drafting
    case_strength = Column(Enum(CaseStrength), nullable=True)  # Set by Reasoning Agent
    urgency = Column(Enum(Urgency), nullable=True)  # Set by Intake Agent

    # Router classification result (full classify_legal_domain output)
    classification = Column(JSONB, nullable=True)  # {domain, intent, confidence, is_civil, reasoning}

    # Agent orchestration
    current_agent = Column(String(50), nullable=True)  # Current agent: "router", "intake", "reasoning", "summary", null

    # Mistral context persistence - store conversation ID to maintain context across messages
    mistral_conversation_id = Column(String(255), nullable=True)  # Mistral's conversation ID for context continuity

    # Conversation state metadata (for dynamic orchestration)
    facts_collected = Column(JSONB, nullable=True)  # All collected facts
    reasoning_done = Column(Boolean, default=False, nullable=False)  # Reasoning completed (renamed from analysis_done)
    summary_generated = Column(Boolean, default=False, nullable=False)  # Summary created

    # Agent progress timestamps (for WS events)
    reasoning_started_at = Column(DateTime(timezone=True), nullable=True)  # When reasoning agent activated
    summary_started_at = Column(DateTime(timezone=True), nullable=True)  # When summary agent activated

    # Missing info tracking (for reminder notifications)
    missing_info = Column(JSONB, nullable=True)  # {"documents": ["rental_contract", "email_copy"]}

    # Structured facts (5W framework)
    who = Column(JSONB, nullable=True)  # Parties involved: {"claimant": "...", "defendant": "..."}
    what = Column(JSONB, nullable=True)  # Issue: {"issue": "...", "legal_area": "...", "specific_problem": "..."}
    when = Column(JSONB, nullable=True)  # Timeline: {"incident_date": "...", "duration": "...", "timeline": [...]}
    where = Column(JSONB, nullable=True)  # Location: {"city": "...", "jurisdiction": "..."}
    why = Column(JSONB, nullable=True)  # Motivation: {"motivation": "...", "desired_outcome": "..."}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Wrap-Up confirmation tracking
    wrapup_confirmed = Column(Boolean, default=False, nullable=False)
    wrapup_content = Column(String, nullable=True)  # Markdown content shown to user
    wrapup_confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Document tracking (from track_documents tool)
    # Stores: {documents: [...], missing_critical_documents: [...], evidence_summary: "..."}
    document_tracker = Column(JSONB, nullable=True)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    summary = relationship("Summary", back_populates="conversation", uselist=False, cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="conversation", cascade="all, delete-orphan")
    lawyer_connections = relationship("LawyerConnection", cascade="all, delete-orphan")
    thinking_steps = relationship("ThinkingSteps", back_populates="conversation", cascade="all, delete-orphan")

    # Indexes (composite indexes for common queries)
    __table_args__ = (
        Index("ix_conversations_user_status", "user_id", "status"),  # List user's active conversations
        Index("ix_conversations_user_created", "user_id", "created_at"),  # List user's recent conversations
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id={self.user_id}, status={self.status})>"
