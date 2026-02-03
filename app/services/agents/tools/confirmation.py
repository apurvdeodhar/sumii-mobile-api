"""Confirmation Detection Tool for Wrap-Up Agent

This tool allows the Wrap-Up agent to signal when user confirms or requests corrections.
Used to trigger handoff to Summary agent or back to Fact Completion.
"""

# Confirmation detection schema - Wrap-Up MUST call this when analyzing user response
CONFIRMATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "signal_confirmation",
        "description": (
            "MANDATORY: Call this function when user responds to the summary confirmation. "
            "Analyze user's response for confirmation or correction signals."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirmed": {
                    "type": "boolean",
                    "description": (
                        "True if user confirmed (Ja, Stimmt, Passt, OK, Richtig, Yes, Correct). "
                        "False if user provided corrections or said no."
                    ),
                },
                "user_response_summary": {
                    "type": "string",
                    "description": "Brief summary of what the user said",
                },
                "corrections_needed": {
                    "type": "string",
                    "description": "If not confirmed, what corrections the user requested. Empty if confirmed.",
                },
            },
            "required": ["confirmed", "user_response_summary"],
        },
    },
}


def get_confirmation_tool() -> dict:
    """Get the confirmation detection tool schema.

    Returns:
        dict: Tool schema for signal_confirmation function
    """
    return CONFIRMATION_SCHEMA
