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
            "have been collected. This identifies what to ask the user about."
        ),
        "parameters": {
            "type": "object",
            "properties": {
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
                "legal_insurance": {
                    "type": "string",
                    "description": "Insurance status (ja/nein). Empty string if not discussed.",
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
                "documents_uploaded": {
                    "type": "boolean",
                    "description": "Whether user has uploaded any documents.",
                },
                "prior_steps_taken": {
                    "type": "string",
                    "description": "Any legal steps already taken. Empty string if not discussed.",
                },
                "missing_critical_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of critical fields still missing. Critical fields: "
                        "client_name, opposing_party, incident_date, desired_outcome."
                    ),
                },
            },
            "required": [
                "client_name",
                "opposing_party",
                "incident_date",
                "desired_outcome",
                "missing_critical_fields",
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
