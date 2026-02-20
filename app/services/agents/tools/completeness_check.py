"""Completeness Check Tool for Wrap-Up Agent

Forces the Wrap-Up agent to systematically audit which fields have been
collected before presenting the summary. The structured schema acts as a
checklist — the LLM fills in what it found from the conversation history
and MANDANTENPROFIL, then reports missing critical fields.

Same pattern as signal_confirmation: not executed server-side, but
structuring it as a tool forces systematic field auditing rather than
relying on vague prompt instructions.
"""

COMPLETENESS_CHECK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_completeness",
        "description": (
            "MANDATORY: Call this function BEFORE presenting the wrap-up summary. "
            "Review the conversation and MANDANTENPROFIL, then report which fields "
            "have been collected. This identifies what to ask the user about. "
            "ALL fields below must be audited — report empty string for any not found."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # --- Core 5W fields ---
                "client_name": {
                    "type": "string",
                    "description": (
                        "Client's full name from MANDANTENPROFIL or conversation. " "Empty string if not found."
                    ),
                },
                "client_address": {
                    "type": "string",
                    "description": "Client's address. Empty string if not found.",
                },
                "opposing_party": {
                    "type": "string",
                    "description": "Name or description of opposing party. Empty string if not found.",
                },
                "incident_date": {
                    "type": "string",
                    "description": "Date of the main incident. Empty string if not found.",
                },
                "desired_outcome": {
                    "type": "string",
                    "description": "What the user wants to achieve. Empty string if not found.",
                },
                # --- German lawyer profile fields (mandatory) ---
                "date_of_birth": {
                    "type": "string",
                    "description": (
                        "Client's date of birth (DD.MM.YYYY). "
                        "Check MANDANTENPROFIL first. Empty string if not found."
                    ),
                },
                "occupation": {
                    "type": "string",
                    "description": (
                        "Client's occupation/profession (Beruf). "
                        "Important for Arbeitsrecht and income-related cases. Empty string if not found."
                    ),
                },
                "legal_insurance": {
                    "type": "string",
                    "description": (
                        "Has Rechtsschutzversicherung? (ja/nein). "
                        "Check MANDANTENPROFIL first. Empty string if not discussed."
                    ),
                },
                "insurance_company": {
                    "type": "string",
                    "description": (
                        "Insurance company name (e.g., ARAG, DEVK, Allianz). "
                        "Check MANDANTENPROFIL first. Empty string if not found."
                    ),
                },
                "insurance_number": {
                    "type": "string",
                    "description": (
                        "Insurance policy number (Versicherungsnummer). "
                        "Check MANDANTENPROFIL first. Empty string if not found."
                    ),
                },
                # --- Case detail fields (mandatory) ---
                "prior_legal_steps": {
                    "type": "string",
                    "description": (
                        "Prior legal steps already taken (e.g., Mängelanzeige sent, lawyer consulted, "
                        "Widerspruch filed, police report). Empty string if not discussed."
                    ),
                },
                "witnesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Names or descriptions of witnesses who can confirm the facts. "
                        "Empty array if none mentioned."
                    ),
                },
                "deadline_info": {
                    "type": "string",
                    "description": (
                        "Known deadlines/Fristen (e.g., Kündigungsfrist, Widerspruchsfrist, "
                        "3-Wochen-Frist Kündigungsschutzklage). "
                        "Empty string if no deadlines known."
                    ),
                },
                # --- Financial info ---
                "financial_claim_value": {
                    "type": "string",
                    "description": (
                        "Estimated claim value in EUR (Streitwert). "
                        "E.g., rent reduction amount, salary claim, damages. Empty string if not discussed."
                    ),
                },
                "financial_claim_description": {
                    "type": "string",
                    "description": (
                        "What the financial claim represents. "
                        "E.g., '3 Monatsmieten Mietminderung', 'Abfindung'. Empty string if not discussed."
                    ),
                },
                # --- Documents ---
                "documents_uploaded": {
                    "type": "boolean",
                    "description": "Whether user has uploaded any documents.",
                },
                # --- Missing fields reports ---
                "missing_critical_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of critical fields still missing. Critical fields include: "
                        "client_name, opposing_party, incident_date, desired_outcome, "
                        "legal_insurance."
                    ),
                },
                "missing_case_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of case detail fields still missing: "
                        "prior_legal_steps, witnesses, deadline_info, "
                        "financial_claim_value, date_of_birth (only if relevant), "
                        "occupation (only if relevant). Report ALL that are empty."
                    ),
                },
                "missing_profile_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of profile fields still missing: "
                        "insurance_company, insurance_number, client_address. "
                        "Report ALL that are empty."
                    ),
                },
            },
            "required": [
                "client_name",
                "opposing_party",
                "incident_date",
                "desired_outcome",
                "date_of_birth",
                "occupation",
                "legal_insurance",
                "prior_legal_steps",
                "witnesses",
                "deadline_info",
                "financial_claim_value",
                "documents_uploaded",
                "missing_critical_fields",
                "missing_case_fields",
                "missing_profile_fields",
            ],
        },
    },
}


def get_completeness_check_tool() -> dict:
    """Get the completeness check tool schema.

    Returns:
        dict: Tool schema for check_completeness function
    """
    return COMPLETENESS_CHECK_SCHEMA
