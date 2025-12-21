"""Documents API - Upload, retrieve, and delete documents"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document, OCRStatus, UploadStatus
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentResponse, DocumentUpdate
from app.services.storage_service import StorageService, get_storage_service
from app.users import current_active_user

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Allowed file types (will be validated server-side with python-magic in TODO 5B.1a)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
}


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: UUID = Form(...),
    run_ocr: bool = Form(False),
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    storage_service: StorageService = Depends(get_storage_service),
):
    """Upload document to S3 and create database record

    Args:
        file: Uploaded file (PDF, JPEG, PNG, HEIC, HEIF)
        conversation_id: Conversation ID this document belongs to
        run_ocr: Whether to run OCR on this document (default: False)

    Returns:
        DocumentResponse with S3 URL

    Raises:
        400: Invalid file type or file too large
        403: User doesn't own this conversation
        404: Conversation not found
    """
    # Verify conversation exists and user owns it
    from app.models.conversation import Conversation

    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to upload to this conversation"
        )

    # Read file content
    file_content = await file.read()

    # Validate file size (10MB limit)
    file_size = len(file_content)
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Maximum size: 10MB")

    # TODO 5B.1a: Add server-side MIME type detection with python-magic
    # For now, trust client MIME type (will be fixed in next TODO)
    file_type = file.content_type or "application/octet-stream"

    if file_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Create document record (upload_status = UPLOADING by default)
    document = Document(
        conversation_id=conversation_id,
        user_id=current_user.id,
        filename=file.filename or "unnamed",
        file_type=file_type,
        file_size=file_size,
        s3_key="",  # Will be set after upload
        s3_url="",  # Will be set after upload
        upload_status=UploadStatus.UPLOADING,
        ocr_status=OCRStatus.PENDING if run_ocr else OCRStatus.COMPLETED,  # Skip OCR if not requested
    )

    db.add(document)
    await db.flush()  # Get document.id without committing

    # Upload to S3
    try:
        s3_key, s3_url = storage_service.upload_document(
            file_content=file_content,
            user_id=current_user.id,
            conversation_id=conversation_id,
            document_id=document.id,
            filename=document.filename,
            content_type=file_type,
        )

        # Update document with S3 info
        document.s3_key = s3_key
        document.s3_url = s3_url
        document.upload_status = UploadStatus.COMPLETED

        await db.commit()
        await db.refresh(document)

        # TODO 5B.3: Trigger OCR processing if run_ocr=True
        # For now, just set status to PENDING

        return document

    except Exception as e:
        # Mark upload as failed
        document.upload_status = UploadStatus.FAILED
        await db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document by ID

    Args:
        document_id: Document UUID

    Returns:
        DocumentResponse with S3 URL

    Raises:
        403: User doesn't own this document
        404: Document not found
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Check ownership
    if document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this document")

    return document


@router.get("/conversation/{conversation_id}", response_model=DocumentListResponse)
async def list_conversation_documents(
    conversation_id: UUID,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents in a conversation

    Args:
        conversation_id: Conversation UUID

    Returns:
        DocumentListResponse with list of documents

    Raises:
        403: User doesn't own this conversation
        404: Conversation not found
    """
    # Verify conversation exists and user owns it
    from app.models.conversation import Conversation

    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this conversation")

    # Get documents ordered by created_at (newest first)
    result = await db.execute(
        select(Document)
        .where(Document.conversation_id == conversation_id, Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()

    return DocumentListResponse(documents=list(documents), total=len(documents))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
    storage_service: StorageService = Depends(get_storage_service),
):
    """Delete document (GDPR compliance)

    Deletes:
    - Document from S3
    - Document record from database

    Args:
        document_id: Document UUID

    Raises:
        403: User doesn't own this document
        404: Document not found
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Check ownership
    if document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this document")

    # Delete from S3
    try:
        storage_service.delete_object(document.s3_key)
    except Exception as e:
        # Log error but continue with database deletion
        print(f"Warning: Failed to delete S3 object {document.s3_key}: {e}")

    # Delete from database
    await db.delete(document)
    await db.commit()

    return None


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Update document metadata",
)
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Update document metadata

    Currently supports updating the filename only.

    Args:
        document_id: Document UUID
        document_data: Fields to update
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated DocumentResponse

    Raises:
        403: User doesn't own this document
        404: Document not found
    """
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Check ownership
    if document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this document")

    # Update fields if provided
    if document_data.filename is not None:
        document.filename = document_data.filename

    await db.commit()
    await db.refresh(document)

    return document
