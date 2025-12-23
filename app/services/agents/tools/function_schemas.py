"""Function schemas for Mistral Agent tool calling

This module defines the function calling schemas used by Mistral agents
for structured data extraction during legal conversations.
"""

# Legal facts extraction schema (Intake Agent)
LEGAL_FACTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_facts",
        "description": "Extract and structure legal facts from conversation",
        "parameters": {
            "type": "object",
            "properties": {
                "who": {
                    "type": "object",
                    "properties": {
                        "plaintiff": {"type": "string", "description": "The person seeking legal help"},
                        "defendant": {"type": "string", "description": "The opposing party"},
                        "witnesses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Any witnesses to the situation",
                        },
                    },
                },
                "what": {
                    "type": "object",
                    "properties": {
                        "legal_area": {
                            "type": "string",
                            "enum": ["Mietrecht", "Arbeitsrecht", "Vertragsrecht", "Other"],
                            "description": "Area of German Civil Law",
                        },
                        "issue_description": {"type": "string", "description": "Brief summary of the legal issue"},
                    },
                },
                "when": {
                    "type": "object",
                    "properties": {
                        "timeline": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string", "description": "ISO date or description"},
                                    "event": {"type": "string", "description": "What happened"},
                                },
                            },
                            "description": "Chronological timeline of events",
                        },
                    },
                },
                "where": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City or federal state in Germany"},
                        "jurisdiction": {"type": "string", "description": "Relevant German federal state"},
                    },
                },
                "why": {
                    "type": "object",
                    "properties": {
                        "desired_outcome": {"type": "string", "description": "What the user wants to achieve"},
                        "urgency": {
                            "type": "string",
                            "enum": ["immediate", "weeks", "months"],
                            "description": "How urgent is the matter",
                        },
                    },
                },
            },
            "required": ["who", "what", "when", "where", "why"],
        },
    },
}

# DEPRECATED: Legal reasoning schema - Sumii does not provide legal analysis
# This schema is kept for backwards compatibility but should not be used
# Legal analysis is done by lawyers, not by Sumii agents
LEGAL_REASONING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "document_collected_facts",
        "description": "Document the facts that have been collected from the user",
        "parameters": {
            "type": "object",
            "properties": {
                "facts_collected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category of fact (documentation, timeline, parties, financial)",
                            },
                            "description": {"type": "string", "description": "The fact that was collected"},
                            "source": {
                                "type": "string",
                                "description": "How this was obtained (user statement, document, etc)",
                            },
                        },
                    },
                    "description": "Facts collected from the user",
                },
                "missing_information": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Information still needed for a lawyer to assess the case",
                },
                "documents_mentioned": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Documents the user mentioned having (contracts, emails, photos, etc)",
                },
            },
            "required": ["facts_collected"],
        },
    },
}

# Summary generation schema (Summary Agent)
# Note: case_strength removed - lawyers assess case strength, not Sumii
SUMMARY_GENERATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_summary",
        "description": "Generate structured factual summary for lawyers in markdown",
        "parameters": {
            "type": "object",
            "properties": {
                "markdown_content": {
                    "type": "string",
                    "description": "Complete markdown summary following the Sumii template structure",
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "legal_area": {"type": "string", "description": "Mietrecht/Arbeitsrecht/etc."},
                        "urgency": {
                            "type": "string",
                            "enum": ["immediate", "weeks", "months"],
                            "description": "Matter urgency",
                        },
                    },
                },
            },
            "required": ["markdown_content", "metadata"],
        },
    },
}
