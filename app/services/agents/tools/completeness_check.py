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
                # --- German lawyer profile fields (OPTIONAL — only ask when case-relevant) ---
                "date_of_birth": {
                    "type": "string",
                    "description": (
                        "Client's date of birth (DD.MM.YYYY). "
                        "ONLY relevant for age-dependent cases (e.g., Jugendarbeitsschutz, Rentenrecht, "
                        "Erbrecht with age thresholds). For most cases (Mietrecht, Vertragsrecht, "
                        "Nebenkostenabrechnung, consumer disputes), DO NOT ask — leave empty. "
                        "Check MANDANTENPROFIL first. Empty string if not found or not relevant."
                    ),
                },
                "occupation": {
                    "type": "string",
                    "description": (
                        "Client's occupation/profession (Beruf). "
                        "ONLY relevant for Arbeitsrecht (employment law) or income-dependent cases "
                        "(e.g., Prozesskostenhilfe, Unterhalt). For most cases (Mietrecht, Vertragsrecht, "
                        "Nebenkostenabrechnung, consumer disputes), DO NOT ask — leave empty. "
                        "Empty string if not found or not relevant."
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
                        "financial_claim_value. "
                        "Do NOT include date_of_birth or occupation here unless "
                        "the case type specifically requires them (Arbeitsrecht, age-dependent law)."
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
                "declined_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Fields the user EXPLICITLY refused to provide. "
                        "Only include if user said 'skip', 'nein', 'möchte ich nicht sagen', "
                        "'I don't want to say', 'weiter', or similar clear refusal. "
                        "Do NOT include fields that simply were not asked yet. "
                        "Possible values: client_name, client_address, opposing_party, "
                        "incident_date, legal_insurance, insurance_company, insurance_number, "
                        "prior_legal_steps, witnesses, deadline_info, financial_claim_value."
                    ),
                },
            },
            "required": [
                "client_name",
                "opposing_party",
                "incident_date",
                "desired_outcome",
                "legal_insurance",
                "prior_legal_steps",
                "witnesses",
                "deadline_info",
                "financial_claim_value",
                "documents_uploaded",
                "missing_critical_fields",
                "missing_case_fields",
                "missing_profile_fields",
                "declined_fields",
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
