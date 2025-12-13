"""Summary Schemas - Request/Response models for summary generation API"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.conversation import CaseStrength, LegalArea, Urgency


class SummaryCreate(BaseModel):
    """Summary generation request schema"""

    conversation_id: UUID


class SummaryResponse(BaseModel):
    """Summary response schema

    Note: Markdown is stored in database AND S3. PDF is stored in S3 only.
    """

    id: UUID
    conversation_id: UUID
    user_id: UUID
    reference_number: str  # SUM-YYYYMMDD-XXXXX (recognizable by German law firms)
    markdown_s3_key: str  # S3 location: summaries/{reference_number}.md
    pdf_s3_key: str  # S3 location: summaries/{reference_number}.pdf
    pdf_url: str  # Pre-signed URL for PDF download (expires after 7 days)
    legal_area: LegalArea
    case_strength: CaseStrength
    urgency: Urgency
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
