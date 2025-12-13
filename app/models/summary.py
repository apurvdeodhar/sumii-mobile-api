"""Summary Model - Store generated legal summaries

Summaries are the final output of the legal intake workflow.
Each conversation has at most one summary (one-to-one relationship).
"""

from uuid import uuid4

from sqlalchemy import UUID, Column, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.conversation import CaseStrength, LegalArea, Urgency


class Summary(Base):
    """Summary model - generated legal summary for conversation

    Attributes:
        id: Unique summary identifier (UUID)
        conversation_id: Foreign key to Conversation (unique, one-to-one)
        user_id: Foreign key to User (for quick user summary queries)
        markdown_content: Full markdown summary text
        pdf_s3_key: S3 object key for PDF version
        pdf_url: Pre-signed or permanent URL for PDF download
        legal_area: Area of German Civil Law (copied from conversation)
        case_strength: Legal case strength (copied from conversation)
        urgency: Matter urgency (copied from conversation)
        created_at: When summary was generated
    """

    __tablename__ = "summaries"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One-to-one: Each conversation has at most one summary
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )  # For quick user summary queries

    # Summary content
    markdown_content = Column(Text, nullable=False)  # Full markdown text

    # Reference number and S3 keys
    reference_number = Column(String(50), nullable=True)  # SUM-YYYYMMDD-XXXXX (recognizable by German law firms)
    markdown_s3_key = Column(String(500), nullable=True)  # S3 location: summaries/{reference_number}.md

    # PDF storage
    pdf_s3_key = Column(String(500), nullable=False)  # S3 object key (e.g., "summaries/{reference_number}.pdf")
    pdf_url = Column(String(1000), nullable=False)  # Pre-signed URL or permanent URL for download

    # Metadata (copied from conversation for easy querying)
    legal_area = Column(Enum(LegalArea), nullable=False)
    case_strength = Column(Enum(CaseStrength), nullable=False)
    urgency = Column(Enum(Urgency), nullable=False)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="summary")
    user = relationship("User", back_populates="summaries")
    lawyer_connections = relationship("LawyerConnection", cascade="all, delete-orphan")

    # Indexes (composite index for user's summary history)
    __table_args__ = (
        Index("ix_summaries_user_created", "user_id", "created_at"),  # List user's summaries by date
    )

    def __repr__(self) -> str:
        return f"<Summary(id={self.id}, conversation_id={self.conversation_id}, legal_area={self.legal_area})>"
