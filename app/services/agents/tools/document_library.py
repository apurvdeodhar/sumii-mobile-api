"""Document Library tool configuration

This module provides the document library tool configuration for Mistral agents,
enabling agents to access the Sumii legal knowledge base.
"""

from app.config import settings


def get_document_library_tool() -> dict:
    """Get document library tool configuration from settings

    Returns:
        dict: Document library tool configuration for Mistral agents

    Example:
        >>> from app.services.agents.tools.document_library import get_document_library_tool
        >>> tools = [get_document_library_tool()]

    Note:
        Mistral API expects 'library_ids' (plural, array) not 'library_id'
    """
    return {
        "type": "document_library",
        "library_ids": [settings.MISTRAL_LIBRARY_ID],  # Array of library IDs
    }
