"""Pydantic validation models for Summary Agent function call output.

These models validate the structured JSON from the generate_summary function call
and auto-fill missing fields from the user's profile data stored in the database.

Also provides ``build_user_profile_context()`` — the single source-of-truth for
formatting a User's profile into a text block consumed by Mistral agents and the
summary context builder.

Usage:
    validated = validate_and_enrich_summary(raw_args, user)
    # validated now has all required fields populated, with user profile fallback
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared profile helpers (used by websocket.py, summary_service.py, and here)
# ---------------------------------------------------------------------------


def _format_address(user: User) -> str:
    """Return comma-separated address or empty string."""
    parts = [p for p in [user.address_street, user.address_postal_code, user.address_city] if p]
    return ", ".join(parts)


def build_user_profile_context(user: User) -> str:
    """Build user profile context string for injecting into Mistral conversation.

    This is the **single source-of-truth** for profile text formatting.  It is
    used both when prepending profile data to the first WS message and when
    building conversation context in SummaryService.

    Args:
        user: User model with profile fields

    Returns:
        Formatted profile text block, or empty string if no profile data.
    """
    parts: list[str] = []
    if user.full_name:
        parts.append(f"Name: {user.full_name}")
    if user.email:
        parts.append(f"E-Mail: {user.email}")
    if user.phone:
        parts.append(f"Telefon: {user.phone}")
    address = _format_address(user)
    if address:
        parts.append(f"Adresse: {address}")
    if user.legal_insurance is not None:
        parts.append(f"Rechtsschutzversicherung: {'Ja' if user.legal_insurance else 'Nein'}")
        if user.legal_insurance:
            if user.insurance_company:
                parts.append(f"Versicherungsgesellschaft: {user.insurance_company}")
            if user.insurance_number:
                parts.append(f"Versicherungsnummer: {user.insurance_number}")

    if not parts:
        return ""

    return "--- MANDANTENPROFIL (Client Profile) ---\n" + "\n".join(parts) + "\n--- ENDE MANDANTENPROFIL ---\n\n"


def build_user_profile_context_lines(user: User) -> list[str]:
    """Return profile as individual lines (for appending to context_parts lists).

    Unlike ``build_user_profile_context`` (which returns a single delimited
    block), this returns bare lines without the MANDANTENPROFIL wrapper — suited
    for the summary service context builder.
    """
    lines: list[str] = []
    if user.full_name:
        lines.append(f"Name: {user.full_name}")
    if user.email:
        lines.append(f"E-Mail: {user.email}")
    if user.phone:
        lines.append(f"Telefon: {user.phone}")
    address = _format_address(user)
    if address:
        lines.append(f"Adresse: {address}")
    if user.legal_insurance is not None:
        lines.append(f"Rechtsschutzversicherung: {'Ja' if user.legal_insurance else 'Nein'}")
        if user.legal_insurance:
            if user.insurance_company:
                lines.append(f"Versicherungsgesellschaft: {user.insurance_company}")
            if user.insurance_number:
                lines.append(f"Versicherungsnummer: {user.insurance_number}")
    return lines


# ---------------------------------------------------------------------------
# Pydantic models — mirror the generate_summary JSON Schema
# ---------------------------------------------------------------------------


class ClientProfile(BaseModel):
    """Mandant (client) profile information"""

    name: str = ""
    address: str = ""
    contact: str = ""


class Claimant(BaseModel):
    """Anspruchsteller (claimant) information"""

    name: str = ""
    role: str = ""
    legal_insurance: str = ""
    insurance_company: str = ""
    insurance_number: str = ""
    date_of_birth: str = ""
    occupation: str = ""


class Respondent(BaseModel):
    """Anspruchsgegner (respondent) information"""

    name: str = ""
    role: str = ""
    address: str = ""
    contact: str = ""


class TimelineEvent(BaseModel):
    """Single event in the chronological timeline"""

    date: str = ""
    event: str = ""
    evidence_ref: str = ""


class FactualNarrative(BaseModel):
    """Sachverhaltsdarstellung - factual case narrative"""

    claimant_goal: str = ""
    party_relationship: str = ""
    chronological_timeline: list[TimelineEvent] = Field(default_factory=list)
    prior_legal_steps: str = ""
    witnesses: list[str] = Field(default_factory=list)
    jurisdiction: str = ""


class EvidenceItem(BaseModel):
    """Single evidence item in the Beweisverzeichnis"""

    anlage_number: str = ""
    document_type: str = ""
    document_date: str = ""
    ocr_extracted_data: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """Beweisverzeichnis - evidence index"""

    evidence_items: list[EvidenceItem] = Field(default_factory=list)


class FinancialInfo(BaseModel):
    """Financial details if applicable"""

    claim_value_eur: str = ""
    claim_description: str = ""


class SummaryMetadata(BaseModel):
    """Summary metadata"""

    legal_area: str = "Mietrecht"
    urgency: str = "weeks"
    case_date: str = ""
    deadline_info: str = ""

    @model_validator(mode="after")
    def set_case_date(self) -> "SummaryMetadata":
        if not self.case_date:
            self.case_date = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        return self


class SummaryData(BaseModel):
    """Complete validated summary data from generate_summary function call.

    All fields have defaults so partial LLM output doesn't crash.
    Missing fields are logged as warnings and auto-filled where possible.
    """

    markdown_content: str = ""
    client_profile: ClientProfile = Field(default_factory=ClientProfile)
    claimant: Claimant = Field(default_factory=Claimant)
    respondent: Respondent = Field(default_factory=Respondent)
    factual_narrative: FactualNarrative = Field(default_factory=FactualNarrative)
    evidence: Evidence = Field(default_factory=Evidence)
    financial_info: FinancialInfo = Field(default_factory=FinancialInfo)
    metadata: SummaryMetadata = Field(default_factory=SummaryMetadata)


# ---------------------------------------------------------------------------
# Validation + enrichment
# ---------------------------------------------------------------------------


def validate_and_enrich_summary(raw_args: dict, user: User | None = None) -> SummaryData:
    """Validate summary function call output and enrich with user profile data.

    Three-layer enforcement:
    1. JSON Schema required arrays (enforced by Mistral during generation)
    2. Pydantic validation (catches any remaining gaps, logs warnings)
    3. Auto-fill from user profile DB data (fills what the LLM missed)

    Args:
        raw_args: Raw JSON dict from generate_summary function call arguments
        user: Optional User model for auto-filling missing profile fields

    Returns:
        SummaryData: Validated and enriched summary data
    """
    # Parse with Pydantic (permissive — all fields have defaults)
    summary = SummaryData.model_validate(raw_args)

    # Track auto-filled fields for logging
    auto_filled: list[str] = []

    # Auto-fill from user profile if available
    if user:
        # Client profile
        if not summary.client_profile.name and user.full_name:
            summary.client_profile.name = user.full_name
            auto_filled.append("client_profile.name")
        if not summary.client_profile.contact and user.email:
            summary.client_profile.contact = user.email
            auto_filled.append("client_profile.contact")
        if not summary.client_profile.address:
            addr = _format_address(user)
            if addr:
                summary.client_profile.address = addr
                auto_filled.append("client_profile.address")

        # Claimant (if LLM didn't populate name, use user profile)
        if not summary.claimant.name and user.full_name:
            summary.claimant.name = user.full_name
            auto_filled.append("claimant.name")
        # Insurance data
        if not summary.claimant.legal_insurance and user.legal_insurance is not None:
            summary.claimant.legal_insurance = "ja" if user.legal_insurance else "nein"
            auto_filled.append("claimant.legal_insurance")
        if user.legal_insurance:
            if not summary.claimant.insurance_company and user.insurance_company:
                summary.claimant.insurance_company = user.insurance_company
                auto_filled.append("claimant.insurance_company")
            if not summary.claimant.insurance_number and user.insurance_number:
                summary.claimant.insurance_number = user.insurance_number
                auto_filled.append("claimant.insurance_number")

    # Log warnings for critical missing fields
    if not summary.markdown_content:
        logger.warning("[SUMMARY_VALIDATION] markdown_content is empty")
    if not summary.claimant.name:
        logger.warning("[SUMMARY_VALIDATION] claimant.name is empty (no user profile fallback available)")
    if not summary.factual_narrative.claimant_goal:
        logger.warning("[SUMMARY_VALIDATION] factual_narrative.claimant_goal is empty")
    if not summary.factual_narrative.chronological_timeline:
        logger.warning("[SUMMARY_VALIDATION] chronological_timeline is empty")

    if auto_filled:
        logger.info(f"[SUMMARY_VALIDATION] Auto-filled {len(auto_filled)} fields from user profile: {auto_filled}")

    return summary
