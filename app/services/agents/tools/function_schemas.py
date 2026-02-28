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
# Structured data for PDF template + markdown for mobile app display
# Note: case_strength removed - lawyers assess case strength, not Sumii
#
# Schema enforces completeness via nested `required` arrays.
# Fields the LLM misses are auto-filled from user profile DB data
# by Pydantic validation in summary_service.py.
SUMMARY_GENERATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_summary",
        "description": (
            "Generate structured factual summary for lawyers with chronological timeline and evidence references. "
            "IMPORTANT: You MUST populate client_profile, claimant, and evidence from the conversation context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                # Human-readable markdown for mobile app bottom sheet
                "markdown_content": {
                    "type": "string",
                    "description": (
                        "Complete markdown summary for mobile display. "
                        "Kurzzusammenfassung MUST answer all 5Ws (who by name, what, when, where, why). "
                        "Chronological timeline entries MUST be detailed (2-3 sentences each, not one-liners). "
                        "Evidence items MUST include OCR-extracted key data."
                    ),
                },
                # Client profile information (Mandant) - from MANDANTENPROFIL in conversation
                "client_profile": {
                    "type": "object",
                    "description": (
                        "Mandant (client) information. MUST be populated from the MANDANTENPROFIL "
                        "provided in the conversation context."
                    ),
                    "properties": {
                        "name": {"type": "string", "description": "Full name of the client (Vor- und Nachname)"},
                        "address": {"type": "string", "description": "Client address (Straße, PLZ, Stadt)"},
                        "contact": {"type": "string", "description": "Email or phone contact"},
                    },
                    "required": ["name"],
                },
                # Structured data for PDF template
                "claimant": {
                    "type": "object",
                    "description": "Anspruchsteller (claimant) information",
                    "properties": {
                        "name": {"type": "string", "description": "Full name of claimant"},
                        "role": {
                            "type": "string",
                            "description": "Role in the matter (e.g., 'Mieter', 'Arbeitnehmer')",
                        },
                        "legal_insurance": {
                            "type": "string",
                            "description": "Rechtsschutzversicherung status (ja/nein/k. A.)",
                        },
                        "insurance_company": {
                            "type": "string",
                            "description": "Name of insurance company (Versicherungsgesellschaft) if applicable",
                        },
                        "insurance_number": {
                            "type": "string",
                            "description": "Insurance policy number (Versicherungsnummer) if applicable",
                        },
                        "date_of_birth": {
                            "type": "string",
                            "description": "Date of birth in DD.MM.YYYY format if provided",
                        },
                        "occupation": {
                            "type": "string",
                            "description": "Occupation/profession (Beruf) if relevant to the case",
                        },
                    },
                    "required": ["name"],
                },
                "respondent": {
                    "type": "object",
                    "description": "Anspruchsgegner (respondent) information",
                    "properties": {
                        "name": {"type": "string", "description": "Name of respondent"},
                        "role": {"type": "string", "description": "Role (e.g., 'Vermieter', 'Arbeitgeber')"},
                        "address": {"type": "string", "description": "Address if known"},
                        "contact": {"type": "string", "description": "Contact info if known"},
                    },
                    "required": ["name"],
                },
                "factual_narrative": {
                    "type": "object",
                    "description": "Sachverhaltsdarstellung - factual case narrative",
                    "properties": {
                        "claimant_goal": {
                            "type": "string",
                            "description": "What the claimant wants (factual, NOT legal assessment)",
                        },
                        "party_relationship": {
                            "type": "string",
                            "description": "Relationship between parties (contract type, duration, etc.)",
                        },
                        "chronological_timeline": {
                            "type": "array",
                            "description": "Events in chronological order with evidence references",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string", "description": "Date in DD.MM.YYYY or description"},
                                    "event": {
                                        "type": "string",
                                        "description": (
                                            "Detailed description of what happened (2-3 sentences). "
                                            "Include: who was involved, what specifically occurred, "
                                            "what the impact was, and any amounts/details from OCR documents. "
                                            "NOT a one-liner like 'Heizung defekt' — instead: "
                                            "'Heizungsausfall in allen drei Räumen (Küche, Bad, Wohnzimmer). "
                                            "Raumtemperatur fällt deutlich ab, Mandant kann nachts nicht schlafen.'"
                                        ),
                                    },
                                    "evidence_ref": {
                                        "type": "string",
                                        "description": "Reference to evidence (e.g., 'Anlage 1' or document name)",
                                    },
                                },
                                "required": ["date", "event"],
                            },
                        },
                        "prior_legal_steps": {
                            "type": "string",
                            "description": (
                                "Prior legal steps already taken (e.g., Mängelanzeige sent, lawyer consulted). "
                                "Factual documentation only."
                            ),
                        },
                        "witnesses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names/descriptions of witnesses if mentioned by user",
                        },
                    },
                    "required": ["claimant_goal", "chronological_timeline"],
                },
                "evidence": {
                    "type": "object",
                    "description": "Beweisverzeichnis - evidence index with OCR-extracted data",
                    "properties": {
                        "evidence_items": {
                            "type": "array",
                            "description": "List of evidence items with OCR-extracted key data",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "anlage_number": {
                                        "type": "string",
                                        "description": "Anlage number (e.g., 'Anlage 1')",
                                    },
                                    "document_type": {
                                        "type": "string",
                                        "description": "Type of document (e.g., 'Mietvertrag', 'Führerschein')",
                                    },
                                    "document_date": {"type": "string", "description": "Date of document if available"},
                                    "ocr_extracted_data": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Key OCR data (e.g., 'Kaltmiete: 850 EUR')",
                                    },
                                },
                                "required": ["anlage_number", "document_type"],
                            },
                        },
                    },
                },
                "financial_info": {
                    "type": "object",
                    "description": "Financial details if applicable",
                    "properties": {
                        "claim_value_eur": {"type": "string", "description": "Estimated claim value in EUR"},
                        "claim_description": {"type": "string", "description": "What the value represents"},
                    },
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
                        "case_date": {
                            "type": "string",
                            "description": "Date of summary generation in DD.MM.YYYY format",
                        },
                        "deadline_info": {
                            "type": "string",
                            "description": (
                                "Known deadlines/Fristen mentioned by user "
                                "(e.g., Kündigungsfrist, Widerspruchsfrist). "
                                "Factual documentation only — no legal assessment of whether they apply."
                            ),
                        },
                    },
                    "required": ["legal_area", "urgency"],
                },
            },
            "required": [
                "markdown_content",
                "client_profile",
                "claimant",
                "respondent",
                "factual_narrative",
                "evidence",
                "metadata",
            ],
        },
    },
}
