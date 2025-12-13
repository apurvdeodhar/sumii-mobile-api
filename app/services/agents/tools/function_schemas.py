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

# Legal reasoning schema (Reasoning Agent)
LEGAL_REASONING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "legal_reasoning",
        "description": "Structure legal analysis with BGB references",
        "parameters": {
            "type": "object",
            "properties": {
                "applicable_laws": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "paragraph": {"type": "string", "description": "BGB paragraph (e.g., § 536 BGB)"},
                            "description": {"type": "string", "description": "What this law covers"},
                            "relevance": {"type": "string", "description": "How it applies to this case"},
                        },
                    },
                    "description": "Relevant BGB paragraphs",
                },
                "case_analysis": {
                    "type": "object",
                    "properties": {
                        "strengths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Strong points in favor of the user",
                        },
                        "weaknesses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Weak points or challenges",
                        },
                        "overall_assessment": {
                            "type": "string",
                            "enum": ["strong", "medium", "weak"],
                            "description": "Overall case strength",
                        },
                    },
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Next steps or recommendations",
                },
            },
            "required": ["applicable_laws", "case_analysis", "recommendations"],
        },
    },
}

# Summary generation schema (Summary Agent)
SUMMARY_GENERATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_summary",
        "description": "Generate structured legal summary in markdown",
        "parameters": {
            "type": "object",
            "properties": {
                "markdown_content": {
                    "type": "string",
                    "description": "Complete markdown summary following the structure",
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "legal_area": {"type": "string", "description": "Mietrecht/Arbeitsrecht/etc."},
                        "case_strength": {
                            "type": "string",
                            "enum": ["strong", "medium", "weak"],
                            "description": "Overall case assessment",
                        },
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
