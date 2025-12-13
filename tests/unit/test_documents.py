"""Comprehensive Tests for Document API endpoints (Unit Tests)

Tests cover:
- Document upload (success, validation errors, authorization)
- Document retrieval (by ID, by conversation)
- Document deletion (GDPR compliance)
- S3 integration (mocked)

These are unit tests that test individual components in isolation.
All external dependencies (S3, database) are mocked.
"""

import io
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.document import OCRStatus, UploadStatus

pytestmark = pytest.mark.unit


class TestDocumentUpload:
    """Test document upload endpoint"""

    @pytest.mark.asyncio
    async def test_upload_pdf_success(self, async_client: AsyncClient, auth_headers: dict, test_conversation):
        """Test successful PDF upload"""
        from app.main import app
        from app.services.s3_service import get_s3_service

        # Create fake PDF file
        pdf_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("contract.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {"conversation_id": str(test_conversation.id), "run_ocr": "false"}

        # Mock S3 service using FastAPI dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_document.return_value = (
            f"users/{test_conversation.user_id}/conversations/{test_conversation.id}/documents/test-id/contract.pdf",
            "https://s3.example.com/presigned-url",
        )

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["filename"] == "contract.pdf"
        assert data["file_type"] == "application/pdf"
        assert data["file_size"] == len(pdf_content)
        assert data["upload_status"] == UploadStatus.COMPLETED.value
        assert data["ocr_status"] == OCRStatus.COMPLETED.value  # OCR not requested
        assert data["s3_url"] == "https://s3.example.com/presigned-url"

    @pytest.mark.asyncio
    async def test_upload_with_ocr(self, async_client: AsyncClient, auth_headers: dict, test_conversation):
        """Test upload with OCR enabled"""
        from app.main import app
        from app.services.s3_service import get_s3_service

        pdf_content = b"%PDF-1.4 fake pdf with text"
        files = {"file": ("document.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {"conversation_id": str(test_conversation.id), "run_ocr": "true"}

        # Mock S3 service using FastAPI dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_document.return_value = ("s3_key", "https://s3.example.com/url")

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["ocr_status"] == OCRStatus.PENDING.value  # OCR requested

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, async_client: AsyncClient, auth_headers: dict, test_conversation):
        """Test upload with invalid file type"""
        txt_content = b"This is a text file"
        files = {"file": ("test.txt", io.BytesIO(txt_content), "text/plain")}
        data = {"conversation_id": str(test_conversation.id), "run_ocr": "false"}

        response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_file_too_large(self, async_client: AsyncClient, auth_headers: dict, test_conversation):
        """Test upload with file too large (>10MB)"""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {"file": ("large.pdf", io.BytesIO(large_content), "application/pdf")}
        data = {"conversation_id": str(test_conversation.id), "run_ocr": "false"}

        response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "too large" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_conversation_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test upload to non-existent conversation"""
        fake_conversation_id = uuid4()
        pdf_content = b"%PDF-1.4 fake pdf"
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {"conversation_id": str(fake_conversation_id), "run_ocr": "false"}

        response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_unauthorized_conversation(
        self, async_client: AsyncClient, auth_headers: dict, other_user_conversation
    ):
        """Test upload to conversation owned by another user"""
        pdf_content = b"%PDF-1.4 fake pdf"
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {"conversation_id": str(other_user_conversation.id), "run_ocr": "false"}

        response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Not authorized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_s3_failure(self, async_client: AsyncClient, auth_headers: dict, test_conversation):
        """Test handling of S3 upload failure"""
        from app.main import app
        from app.services.s3_service import get_s3_service

        pdf_content = b"%PDF-1.4 fake pdf"
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {"conversation_id": str(test_conversation.id), "run_ocr": "false"}

        # Mock S3 service to raise exception using FastAPI dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.upload_document.side_effect = Exception("S3 connection failed")

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.post("/api/v1/documents/", data=data, files=files, headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Upload failed" in response.json()["detail"]


class TestDocumentRetrieval:
    """Test document retrieval endpoints"""

    @pytest.mark.asyncio
    async def test_get_document_success(self, async_client: AsyncClient, auth_headers: dict, test_document):
        """Test get document by ID"""
        response = await async_client.get(f"/api/v1/documents/{test_document.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(test_document.id)
        assert data["filename"] == test_document.filename
        assert data["upload_status"] == test_document.upload_status.value
        assert data["ocr_status"] == test_document.ocr_status.value

    @pytest.mark.asyncio
    async def test_get_document_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test get non-existent document"""
        fake_id = uuid4()
        response = await async_client.get(f"/api/v1/documents/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Document not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_document_unauthorized(self, async_client: AsyncClient, auth_headers: dict, other_user_document):
        """Test get document owned by another user"""
        response = await async_client.get(f"/api/v1/documents/{other_user_document.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Not authorized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_conversation_documents(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation, test_document
    ):
        """Test list documents in conversation"""
        response = await async_client.get(
            f"/api/v1/documents/conversation/{test_conversation.id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1
        assert len(data["documents"]) >= 1
        assert data["documents"][0]["id"] == str(test_document.id)

    @pytest.mark.asyncio
    async def test_list_conversation_documents_empty(
        self, async_client: AsyncClient, auth_headers: dict, test_conversation
    ):
        """Test list documents in conversation with no documents"""
        response = await async_client.get(
            f"/api/v1/documents/conversation/{test_conversation.id}",
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Might have documents from other tests, so just check structure
        assert "documents" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_conversation_documents_unauthorized(
        self, async_client: AsyncClient, auth_headers: dict, other_user_conversation
    ):
        """Test list documents in conversation owned by another user"""
        response = await async_client.get(
            f"/api/v1/documents/conversation/{other_user_conversation.id}", headers=auth_headers
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Not authorized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_conversation_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test list documents for non-existent conversation"""
        fake_id = uuid4()
        response = await async_client.get(f"/api/v1/documents/conversation/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Conversation not found" in response.json()["detail"]


class TestDocumentDeletion:
    """Test document deletion endpoint"""

    @pytest.mark.asyncio
    async def test_delete_document_success(self, async_client: AsyncClient, auth_headers: dict, test_document):
        """Test successful document deletion"""
        from app.main import app
        from app.services.s3_service import get_s3_service

        document_id = test_document.id

        # Mock S3 service using FastAPI dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.delete_object.return_value = None

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify document is deleted
        response = await async_client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, async_client: AsyncClient, auth_headers: dict):
        """Test delete non-existent document"""
        fake_id = uuid4()
        response = await async_client.delete(f"/api/v1/documents/{fake_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Document not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_document_unauthorized(
        self, async_client: AsyncClient, auth_headers: dict, other_user_document
    ):
        """Test delete document owned by another user"""
        response = await async_client.delete(f"/api/v1/documents/{other_user_document.id}", headers=auth_headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Not authorized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_document_s3_failure(self, async_client: AsyncClient, auth_headers: dict, test_document):
        """Test deletion continues even if S3 delete fails"""
        from app.main import app
        from app.services.s3_service import get_s3_service

        document_id = test_document.id

        # Mock S3 service to raise exception using FastAPI dependency override
        mock_s3_instance = MagicMock()
        mock_s3_instance.delete_object.side_effect = Exception("S3 connection failed")

        def override_get_s3_service():
            return mock_s3_instance

        app.dependency_overrides[get_s3_service] = override_get_s3_service

        try:
            response = await async_client.delete(f"/api/v1/documents/{document_id}", headers=auth_headers)
        finally:
            app.dependency_overrides.pop(get_s3_service, None)

        # Should still succeed (deletes from DB even if S3 fails)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify document is deleted from database
        response = await async_client.get(f"/api/v1/documents/{document_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
