"""Comprehensive Tests for Summary API endpoints (Unit Tests)

Tests cover:
- Summary generation (success, duplicate, authorization, errors)
- Summary retrieval (by conversation, list all, PDF URL)
- Authorization checks (403 for other user's summaries)
- S3 integration (mocked)
- PDF generation (mocked)
- Mistral Agent integration (mocked)

These are unit tests that test individual components in isolation.
All external dependencies (S3, PDFService, Mistral Agents) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.conversation import CaseStrength, LegalArea, Urgency
from app.models.message import Message, MessageRole
from app.models.summary import Summary

pytestmark = pytest.mark.unit


class TestSummaryGeneration:
    """Test summary generation endpoint (POST /api/v1/summaries)"""

    @pytest.mark.asyncio
    async def test_generate_summary_success(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, db_session
    ):
        """Test successful summary generation"""
        # Add some messages to conversation
        user_message = Message(
            conversation_id=test_conversation.id,
            role=MessageRole.USER,
            content="Ich habe ein Problem mit meiner Miete.",
        )
        ai_message = Message(
            conversation_id=test_conversation.id,
            role=MessageRole.ASSISTANT,
            content="Können Sie mir mehr Details geben?",
            agent_name="intake",
        )
        db_session.add_all([user_message, ai_message])
        await db_session.commit()

        # Mock services using FastAPI dependency override and patching
        from app.main import app
        from app.services.agents import get_mistral_agents_service
        from app.services.s3_service import get_s3_service

        # Mock agents service using dependency override
        mock_agents_instance = MagicMock()
        mock_agents_instance.get_agent_id.return_value = "summary-agent-id"

        def override_get_mistral_agents_service():
            return mock_agents_instance

        # Mock S3 service using dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_summary.side_effect = [
            ("summaries/SUM-20250127-ABC12.md", "https://s3.example.com/markdown"),
            ("summaries/SUM-20250127-ABC12.pdf", "https://s3.example.com/pdf"),
        ]
        mock_s3_instance.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        def override_get_s3_service():
            return mock_s3_instance

        # Mock summary service (called directly, not a dependency)
        mock_summary_service_instance = AsyncMock()
        mock_summary_service_instance.generate_summary.return_value = (
            "# Rechtliche Zusammenfassung\n\n## 1. Sachverhalt\nTest content",
            {"legal_area": "Mietrecht", "case_strength": "strong", "urgency": "weeks"},
        )

        app.dependency_overrides[get_mistral_agents_service] = override_get_mistral_agents_service
        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            # Mock summary service and PDFService
            # PDFService is lazily imported inside the function, so we need to patch
            # the module before the import happens
            import sys
            import types

            # Create a mock PDFService class that won't trigger WeasyPrint import
            class MockPDFService:
                def __init__(self):
                    pass

                def markdown_to_pdf(self, content: str, reference_number: str = None) -> bytes:
                    return b"%PDF-1.4 fake pdf"

            # Create a mock pdf_service module if it doesn't exist
            if "app.services.pdf_service" not in sys.modules:
                mock_module = types.ModuleType("app.services.pdf_service")
                mock_module.PDFService = MockPDFService  # type: ignore[attr-defined]
                sys.modules["app.services.pdf_service"] = mock_module
            else:
                # Patch existing module
                original_module = sys.modules["app.services.pdf_service"]
                setattr(original_module, "PDFService", MockPDFService)

            with patch("app.api.v1.summaries.get_summary_service") as mock_summary_service:
                mock_summary_service.return_value = mock_summary_service_instance

                # Make request
                response = await async_client.post(
                    "/api/v1/summaries",
                    json={"conversation_id": str(test_conversation.id)},
                    headers=auth_headers,
                )

            # Restore original if it existed
            if "app.services.pdf_service" in sys.modules:
                original_module = sys.modules["app.services.pdf_service"]
                if hasattr(original_module, "_original_pdf_class"):
                    setattr(original_module, "PDFService", original_module._original_pdf_class)
        finally:
            app.dependency_overrides.pop(get_mistral_agents_service, None)
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["conversation_id"] == str(test_conversation.id)
        assert data["legal_area"] == LegalArea.MIETRECHT.value
        assert data["case_strength"] == CaseStrength.STRONG.value
        assert data["urgency"] == Urgency.WEEKS.value
        assert "reference_number" in data
        assert data["reference_number"].startswith("SUM-")
        assert "pdf_url" in data
        assert "markdown_s3_key" in data
        assert "pdf_s3_key" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_generate_summary_duplicate(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, db_session
    ):
        """Test that generating summary for conversation with existing summary returns existing"""
        # Create existing summary
        existing_summary = Summary(
            conversation_id=test_conversation.id,
            user_id=test_conversation.user_id,
            markdown_content="# Existing Summary",
            reference_number="SUM-20250127-EXIST",
            markdown_s3_key="summaries/SUM-20250127-EXIST.md",
            pdf_s3_key="summaries/SUM-20250127-EXIST.pdf",
            pdf_url="https://s3.example.com/existing.pdf",
            legal_area=LegalArea.MIETRECHT,
            case_strength=CaseStrength.MEDIUM,
            urgency=Urgency.WEEKS,
        )
        db_session.add(existing_summary)
        await db_session.commit()

        # Mock S3 service using FastAPI dependency override
        from app.main import app
        from app.services.s3_service import get_s3_service

        mock_s3_instance = MagicMock()
        mock_s3_instance.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            # Make request
            response = await async_client.post(
                "/api/v1/summaries",
                json={"conversation_id": str(test_conversation.id)},
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["reference_number"] == "SUM-20250127-EXIST"
        assert data["conversation_id"] == str(test_conversation.id)

    @pytest.mark.asyncio
    async def test_generate_summary_conversation_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test generating summary for non-existent conversation returns 404"""
        fake_conversation_id = str(uuid4())

        response = await async_client.post(
            "/api/v1/summaries",
            json={"conversation_id": fake_conversation_id},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_generate_summary_unauthorized(
        self, async_client: AsyncClient, auth_headers: dict, other_user_conversation
    ):
        """Test generating summary for another user's conversation returns 403"""
        response = await async_client.post(
            "/api/v1/summaries",
            json={"conversation_id": str(other_user_conversation.id)},
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_generate_summary_agent_error(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, db_session
    ):
        """Test summary generation failure returns 500"""
        # Add messages
        user_message = Message(
            conversation_id=test_conversation.id,
            role=MessageRole.USER,
            content="Test message",
        )
        db_session.add(user_message)
        await db_session.commit()

        # Mock summary service to raise error
        with (
            patch("app.api.v1.summaries.get_mistral_agents_service") as mock_agents,
            patch("app.api.v1.summaries.get_summary_service") as mock_summary_service,
        ):
            mock_agents_instance = MagicMock()
            mock_agents_instance.get_agent_id.return_value = "summary-agent-id"
            mock_agents.return_value = mock_agents_instance

            mock_summary_service_instance = AsyncMock()
            mock_summary_service_instance.generate_summary.side_effect = Exception("Agent error")
            mock_summary_service.return_value = mock_summary_service_instance

            response = await async_client.post(
                "/api/v1/summaries",
                json={"conversation_id": str(test_conversation.id)},
                headers=auth_headers,
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "failed" in response.json()["detail"].lower()


class TestSummaryRetrieval:
    """Test summary retrieval endpoints"""

    @pytest.mark.asyncio
    async def test_get_summary_by_conversation(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, db_session
    ):
        """Test getting summary by conversation ID"""
        # Create summary
        summary = Summary(
            conversation_id=test_conversation.id,
            user_id=test_conversation.user_id,
            markdown_content="# Test Summary",
            reference_number="SUM-20250127-TEST1",
            markdown_s3_key="summaries/SUM-20250127-TEST1.md",
            pdf_s3_key="summaries/SUM-20250127-TEST1.pdf",
            pdf_url="https://s3.example.com/test.pdf",
            legal_area=LegalArea.MIETRECHT,
            case_strength=CaseStrength.STRONG,
            urgency=Urgency.IMMEDIATE,
        )
        db_session.add(summary)
        await db_session.commit()

        # Mock S3 service using FastAPI dependency override
        from app.main import app
        from app.services.s3_service import get_s3_service

        mock_s3_instance = MagicMock()
        mock_s3_instance.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.get(
                f"/api/v1/summaries/conversation/{test_conversation.id}",
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["conversation_id"] == str(test_conversation.id)
        assert data["reference_number"] == "SUM-20250127-TEST1"
        assert data["legal_area"] == LegalArea.MIETRECHT.value
        assert data["case_strength"] == CaseStrength.STRONG.value
        assert data["urgency"] == Urgency.IMMEDIATE.value

    @pytest.mark.asyncio
    async def test_get_summary_by_conversation_not_found(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation
    ):
        """Test getting summary for conversation without summary returns 404"""
        response = await async_client.get(
            f"/api/v1/summaries/conversation/{test_conversation.id}",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_summary_by_conversation_unauthorized(
        self, async_client: AsyncClient, auth_headers: dict, other_user_conversation, db_session
    ):
        """Test getting summary for another user's conversation returns 403"""
        # Create summary for other user
        summary = Summary(
            conversation_id=other_user_conversation.id,
            user_id=other_user_conversation.user_id,
            markdown_content="# Other User Summary",
            reference_number="SUM-20250127-OTHER",
            markdown_s3_key="summaries/SUM-20250127-OTHER.md",
            pdf_s3_key="summaries/SUM-20250127-OTHER.pdf",
            pdf_url="https://s3.example.com/other.pdf",
            legal_area=LegalArea.ARBEITSRECHT,
            case_strength=CaseStrength.MEDIUM,
            urgency=Urgency.WEEKS,
        )
        db_session.add(summary)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/summaries/conversation/{other_user_conversation.id}",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_summaries(
        self, async_client: AsyncClient, auth_headers: dict, test_user, db_session, test_conversation
    ):
        """Test listing all summaries for authenticated user"""
        # Create multiple summaries
        summary1 = Summary(
            conversation_id=test_conversation.id,
            user_id=test_user.id,
            markdown_content="# Summary 1",
            reference_number="SUM-20250127-001",
            markdown_s3_key="summaries/SUM-20250127-001.md",
            pdf_s3_key="summaries/SUM-20250127-001.pdf",
            pdf_url="https://s3.example.com/summary1.pdf",
            legal_area=LegalArea.MIETRECHT,
            case_strength=CaseStrength.STRONG,
            urgency=Urgency.IMMEDIATE,
        )

        # Create another conversation and summary
        from app.models.conversation import Conversation, ConversationStatus

        conversation2 = Conversation(
            user_id=test_user.id, title="Second Conversation", status=ConversationStatus.ACTIVE
        )
        db_session.add(conversation2)
        await db_session.flush()

        summary2 = Summary(
            conversation_id=conversation2.id,
            user_id=test_user.id,
            markdown_content="# Summary 2",
            reference_number="SUM-20250127-002",
            markdown_s3_key="summaries/SUM-20250127-002.md",
            pdf_s3_key="summaries/SUM-20250127-002.pdf",
            pdf_url="https://s3.example.com/summary2.pdf",
            legal_area=LegalArea.ARBEITSRECHT,
            case_strength=CaseStrength.MEDIUM,
            urgency=Urgency.WEEKS,
        )

        db_session.add_all([summary1, summary2])
        await db_session.commit()

        # Mock S3 service using FastAPI dependency override
        from app.main import app
        from app.services.s3_service import get_s3_service

        mock_s3_instance = MagicMock()
        mock_s3_instance.generate_presigned_url.return_value = "https://s3.example.com/presigned"

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.get("/api/v1/summaries", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # Should be ordered by created_at DESC (newest first)
        assert data[0]["reference_number"] in ["SUM-20250127-001", "SUM-20250127-002"]
        assert data[1]["reference_number"] in ["SUM-20250127-001", "SUM-20250127-002"]

    @pytest.mark.asyncio
    async def test_list_summaries_empty(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing summaries when user has none returns empty list"""
        response = await async_client.get("/api/v1/summaries", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_summary_pdf_url(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, db_session
    ):
        """Test getting pre-signed PDF URL"""
        # Create summary
        summary = Summary(
            conversation_id=test_conversation.id,
            user_id=test_conversation.user_id,
            markdown_content="# Test Summary",
            reference_number="SUM-20250127-PDF",
            markdown_s3_key="summaries/SUM-20250127-PDF.md",
            pdf_s3_key="summaries/SUM-20250127-PDF.pdf",
            pdf_url="https://s3.example.com/old.pdf",
            legal_area=LegalArea.MIETRECHT,
            case_strength=CaseStrength.STRONG,
            urgency=Urgency.WEEKS,
        )
        db_session.add(summary)
        await db_session.commit()

        # Mock S3 service using FastAPI dependency override
        from app.main import app
        from app.services.s3_service import get_s3_service

        mock_s3_instance = MagicMock()
        mock_s3_instance.generate_presigned_url.return_value = "https://s3.example.com/new-presigned-url"

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.get(
                f"/api/v1/summaries/{summary.id}/pdf",
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "pdf_url" in data
        assert data["pdf_url"] == "https://s3.example.com/new-presigned-url"

    @pytest.mark.asyncio
    async def test_get_summary_pdf_url_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting PDF URL for non-existent summary returns 404"""
        fake_summary_id = str(uuid4())

        response = await async_client.get(
            f"/api/v1/summaries/{fake_summary_id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_summary_pdf_url_unauthorized(
        self, async_client: AsyncClient, auth_headers: dict, other_user_conversation, db_session
    ):
        """Test getting PDF URL for another user's summary returns 403"""
        # Create summary for other user
        summary = Summary(
            conversation_id=other_user_conversation.id,
            user_id=other_user_conversation.user_id,
            markdown_content="# Other Summary",
            reference_number="SUM-20250127-OTHER",
            markdown_s3_key="summaries/SUM-20250127-OTHER.md",
            pdf_s3_key="summaries/SUM-20250127-OTHER.pdf",
            pdf_url="https://s3.example.com/other.pdf",
            legal_area=LegalArea.MIETRECHT,
            case_strength=CaseStrength.MEDIUM,
            urgency=Urgency.WEEKS,
        )
        db_session.add(summary)
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/summaries/{summary.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in response.json()["detail"].lower()


class TestSummaryAuthorization:
    """Test authorization for summary endpoints"""

    @pytest.mark.asyncio
    async def test_summary_endpoints_require_auth(self, db_session, test_conversation):
        """Test that all summary endpoints require authentication"""
        # Create a client WITHOUT auth override (to test real auth)
        from httpx import ASGITransport, AsyncClient

        from app.database import get_db
        from app.main import app

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        # Don't override get_current_user - let it fail naturally

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Test POST
            response = await client.post(
                "/api/v1/summaries",
                json={"conversation_id": str(test_conversation.id)},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test GET by conversation
            response = await client.get(f"/api/v1/summaries/conversation/{test_conversation.id}")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test GET list
            response = await client.get("/api/v1/summaries")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test GET PDF URL
            fake_id = str(uuid4())
            response = await client.get(f"/api/v1/summaries/{fake_id}/pdf")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        app.dependency_overrides.clear()
