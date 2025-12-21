"""Mistral Document Library Management

Programmatic management of Mistral AI Document Libraries for RAG (Retrieval-Augmented Generation).
Provides interviewing skills, real-world examples, and summary templates to agents.
"""

from pathlib import Path

from mistralai import Mistral
from mistralai.models import File

from app.config import settings


class DocumentLibraryService:
    """Manage Mistral document libraries programmatically

    This service creates and manages document libraries for the Sumii lawyer assistant platform.
    Libraries are shared with agents to provide them with interviewing skills, real-world examples,
    and templates for generating lawyer-ready summaries.

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
            name="Sumii Interviewing & Summary Knowledge Base",
            description=(
                "Interviewing skills, real-world examples, " "and lawyer-ready summary templates for Sumii AI agents"
            ),
        )

        self.library_id = library.id
        return library.id

    def upload_interviewing_skills(self) -> None:
        """Upload interviewing skills guide to library

        Uploads empathetic interviewing techniques and questioning frameworks for legal situations.
        This provides agents with knowledge on how to gather facts without overwhelming users.

        Raises:
            FileNotFoundError: If interviewing skills file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        skills_path = Path("docs/library/interviewing_skills.md")

        if not skills_path.exists():
            raise FileNotFoundError(f"Interviewing skills file not found: {skills_path}")

        with open(skills_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=skills_path.name, content=f.read()),
            )

    def upload_lawyer_ready_summaries_guide(self) -> None:
        """Upload lawyer-ready summaries guide

        Uploads the guide on format and structure for creating summaries that lawyers can quickly understand.
        This provides agents with knowledge on how to structure information for legal professionals.

        Raises:
            FileNotFoundError: If summaries guide file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        summaries_guide_path = Path("docs/library/lawyer_ready_summaries.md")

        if not summaries_guide_path.exists():
            raise FileNotFoundError(f"Lawyer-ready summaries guide file not found: {summaries_guide_path}")

        with open(summaries_guide_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=summaries_guide_path.name, content=f.read()),
            )

    def upload_legal_template(self) -> None:
        """Upload Sumii case report template

        Uploads the template that Summary Agent uses to generate
        summaries in the correct format.

        Raises:
            FileNotFoundError: If template file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        template_path = Path("docs/library/templates/SumiiCaseReportTemplate.md")

        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        with open(template_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=template_path.name, content=f.read()),
            )

    def upload_real_world_examples(self) -> None:
        """Upload real-world interview examples

        Uploads examples of successful empathetic interviews with users in legal situations.
        Provides agents with concrete examples of how to gather facts naturally.

        Raises:
            FileNotFoundError: If real-world examples file doesn't exist
            Exception: If upload fails
        """
        if not self.library_id:
            raise ValueError("Library must be created before uploading documents")

        examples_path = Path("docs/library/real_world_examples.md")

        if not examples_path.exists():
            raise FileNotFoundError(f"Real-world examples file not found: {examples_path}")

        with open(examples_path, "rb") as f:
            self.client.beta.libraries.documents.upload(
                library_id=self.library_id,
                file=File(file_name=examples_path.name, content=f.read()),
            )

    def setup_mvp_library(self) -> str:
        """Create MVP library with essential content

        Minimal viable library:
        1. Creates library
        2. Uploads interviewing skills guide
        3. Uploads lawyer-ready summaries guide
        4. Uploads legal template

        Returns:
            library_id: ID of the configured library

        Raises:
            Exception: If any step fails
        """
        # Create library
        library_id = self.create_sumii_library()

        # Upload essential content
        self.upload_interviewing_skills()
        self.upload_lawyer_ready_summaries_guide()
        self.upload_legal_template()

        return library_id

    def setup_complete_library(self) -> str:
        """Create library and upload all documents

        Complete library for production use:
        1. Creates a new Mistral document library
        2. Uploads interviewing skills guide
        3. Uploads real-world examples
        4. Uploads lawyer-ready summaries guide
        5. Uploads legal template

        Returns:
            library_id: ID of the configured library

        Raises:
            Exception: If any step fails
        """
        # Create library
        library_id = self.create_sumii_library()

        # Upload all documents
        self.upload_interviewing_skills()
        self.upload_real_world_examples()
        self.upload_lawyer_ready_summaries_guide()
        self.upload_legal_template()

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
