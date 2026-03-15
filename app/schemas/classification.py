"""Classification Pydantic Schemas — Domain and intent classification for Router Agent

The Router agent calls `classify_legal_domain` to classify the user's legal domain
and intent. These schemas model the classification result stored on Conversation.
"""

from enum import Enum as PyEnum

from pydantic import BaseModel, Field


class LegalDomain(str, PyEnum):
    """German Civil Law domains (Nick's taxonomy, March 8 2026)

    8 domains covering the full scope of Sumii's civil law intake.
    """

    VERTRAGSRECHT = "vertragsrecht"  # Contract Law
    MIETRECHT = "mietrecht"  # Tenancy Law
    ARBEITSRECHT = "arbeitsrecht"  # Employment Law
    FAMILIENRECHT = "familienrecht"  # Family Law
    ERBRECHT = "erbrecht"  # Succession / Inheritance
    DELIKTSRECHT = "deliktsrecht"  # Tort Law (Wrongdoing)
    SACHENRECHT = "sachenrecht"  # Property Law (Immobiliar)
    GESELLSCHAFTSRECHT = "gesellschaftsrecht"  # Company Law


class UserIntent(str, PyEnum):
    """Two-dimensional intent classification (Nick's taxonomy)

    Determines the questioning style: fact-gathering vs requirements-gathering.
    """

    DISPUTE = "dispute"  # Concrete case / active problem (Ask/Claim)
    DRAFTING = "drafting"  # Document drafting / creation (Action/Draft)


class DomainClassification(BaseModel):
    """Router's classification result — stored as JSONB on Conversation

    The Router agent calls `classify_legal_domain` which returns this structure.
    Confidence threshold: >= 0.7 routes to domain agent, < 0.7 falls back to generic intake.
    """

    domain: LegalDomain = Field(description="Classified legal domain")
    intent: UserIntent = Field(description="User's intent: dispute or drafting")
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence (0-1)")
    is_civil: bool = Field(default=True, description="Whether this is civil law (Sumii's scope)")
    reasoning: str | None = Field(default=None, description="Brief reasoning for classification")
