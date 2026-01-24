"""Document Tracking Tool for Wrap-Up Agent

This tool tracks documents mentioned in conversation vs their upload status.
Enables:
1. Future app notifications for missing documents
2. Structured evidence index for Summary
3. Evidence ↔ facts ↔ reasoning linkage
"""

# Document tracking schema - captures document status at wrap-up phase
DOCUMENT_TRACKER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "track_documents",
        "description": (
            "Track documents mentioned during conversation compared to what was uploaded. "
            "Call this to create a structured evidence index before summary generation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "documents": {
                    "type": "array",
                    "description": "All documents discussed in the conversation",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Document name (e.g., 'Mietvertrag', 'Führerschein')",
                            },
                            "document_type": {
                                "type": "string",
                                "enum": [
                                    "contract",
                                    "letter",
                                    "email",
                                    "photo",
                                    "id_document",
                                    "receipt",
                                    "other",
                                ],
                                "description": "Type of document",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["uploaded", "mentioned_not_uploaded", "requested"],
                                "description": (
                                    "uploaded = user uploaded file, "
                                    "mentioned_not_uploaded = user mentioned having it but didn't upload, "
                                    "requested = agent asked user to provide"
                                ),
                            },
                            "linked_facts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Facts this document supports (e.g., 'rent amount', 'timeline')",
                            },
                            "ocr_summary": {
                                "type": "string",
                                "description": "Key info extracted from OCR if uploaded",
                            },
                        },
                        "required": ["name", "document_type", "status"],
                    },
                },
                "missing_critical_documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Documents that would strengthen the case but weren't uploaded. "
                        "E.g., 'Mängelanzeige per E-Mail' if user mentioned sending but didn't upload."
                    ),
                },
                "evidence_summary": {
                    "type": "string",
                    "description": "Brief summary of evidence status for lawyer review",
                },
            },
            "required": ["documents", "evidence_summary"],
        },
    },
}


def get_document_tracker_tool() -> dict:
    """Get the document tracking tool schema.

    Returns:
        dict: Tool schema for track_documents function
    """
    return DOCUMENT_TRACKER_SCHEMA
