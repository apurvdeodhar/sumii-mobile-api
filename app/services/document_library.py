"""Mistral Document Library Management

Programmatic management of Mistral AI Document Libraries for RAG (Retrieval-Augmented Generation).
Provides BGB legal knowledge, case examples, and templates to agents.
"""

from pathlib import Path

from mistralai import Mistral
from mistralai.models import File

from app.config import settings


class DocumentLibraryService:
    """Manage Mistral document libraries programmatically

    This service creates and manages document libraries for the Sumii legal AI platform.
    Libraries are shared with agents to provide them with legal knowledge (BGB sections),
    case examples, and templates for generating summaries.

    Attributes:
        client: Mistral AI client instance
        library_id: ID of the created/managed library (set after creation)
    """

    def __init__(self):
        """Initialize the Document Library Service with Mistral client"""
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.library_id: str | None = None

    def create_sumii_library(self) -> str:
        """Create Sumii legal knowledge library

        Creates a new document library in Mistral AI for storing legal knowledge.
        The library is shared with the organization so agents can access it.

        Returns:
            library_id: ID of the created library

        Raises:
            Exception: If library creation fails
        """
        # Create library
        library = self.client.beta.libraries.create(
            name="Sumii Legal Knowledge Base",
            description="German civil law (BGB), case examples, and legal templates for Sumii AI agents",
        )

        self.library_id = library.id
        return library.id

    def upload_bgb_sections(self) -> None:
        """Upload BGB Mietrecht sections to library

        Uploads German Civil Code (BGB) rental law sections (§535-§577a) to the library.
        This provides agents with legal knowledge for analyzing rental law cases.

        Raises:
            FileNotFoundError: If BGB sections file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        # Phase 2: Complete library
        bgb_path = Path("docs/library/bgb_mietrecht_sections.md")

        if not bgb_path.exists():
            raise FileNotFoundError(f"BGB sections file not found: {bgb_path}")

        with open(bgb_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=bgb_path.name, content=f.read()),
            )

    def upload_legal_template(self) -> None:
        """Upload Sumii case report template

        Uploads the forensic analysis template that Summary Agent uses to generate
        legal summaries in the correct format.

        Raises:
            FileNotFoundError: If template file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        # Phase 1: MVP library (existing template)
        template_path = Path("docs/library/templates/SumiiCaseReportTemplate.md")

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        with open(template_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=template_path.name, content=f.read()),
            )

    def upload_case_examples(self) -> None:
        """Upload case law examples

        Uploads example court rulings (BGH decisions) for rental law cases.
        Provides agents with precedents for legal analysis.

        Raises:
            FileNotFoundError: If case examples file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        # Phase 2: Complete library
        cases_path = Path("docs/library/case_examples_mietrecht.md")

        if not cases_path.exists():
            raise FileNotFoundError(f"Case examples file not found: {cases_path}")

        with open(cases_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=cases_path.name, content=f.read()),
            )

    def setup_mvp_library(self) -> str:
        """Create MVP library with template only (Phase 1)

        Minimal viable library for initial testing:
        1. Creates library
        2. Uploads legal template only

        Returns:
            library_id: ID of the configured library

        Raises:
            Exception: If any step fails
        """
        # Create library
        library_id = self.create_sumii_library()

        # Phase 1: Upload template only
        self.upload_legal_template()

        return library_id

    def setup_complete_library(self) -> str:
        """Create library and upload all documents (Phase 2)

        Complete library for production use:
        1. Creates a new Mistral document library
        2. Uploads BGB sections
        3. Uploads legal template
        4. Uploads case examples

        Returns:
            library_id: ID of the configured library

        Raises:
            Exception: If any step fails
        """
        # Create library
        library_id = self.create_sumii_library()

        # Phase 2: Upload all documents
        self.upload_bgb_sections()
        self.upload_legal_template()
        self.upload_case_examples()

        return library_id

    def get_library_info(self) -> dict:
        """Get information about the current library

        Returns:
            dict: Library information including name, description, document count

        Raises:
            ValueError: If no library_id is set
        """
        if not self.library_id:
            raise ValueError("No library ID set. Create a library first.")

        library = self.client.beta.libraries.get(library_id=self.library_id)
        return {
            "id": library.id,
            "name": library.name,
            "description": library.description,
            "created_at": library.created_at if hasattr(library, "created_at") else None,
        }


# Dependency injection
def get_document_library_service() -> DocumentLibraryService:
    """Get DocumentLibraryService instance for dependency injection

    Returns:
        DocumentLibraryService: New service instance
    """
    return DocumentLibraryService()
