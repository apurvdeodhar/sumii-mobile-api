"""Document Model - Store uploaded documents (PDFs, images, etc.)

Documents can be uploaded by users as evidence for their legal cases.
Each document belongs to a conversation and user, stored in S3, with OCR processing.

Status Flow:
1. upload_status: uploading → completed (S3 upload)
2. ocr_status: pending → processing → completed (OCR processing)
"""

import uuid
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class UploadStatus(str, PyEnum):
    """S3 upload status"""

    UPLOADING = "uploading"  # Upload to S3 in progress
    COMPLETED = "completed"  # Upload to S3 completed
    FAILED = "failed"  # Upload to S3 failed


class OCRStatus(str, PyEnum):
    """OCR processing status"""

    PENDING = "pending"  # OCR not yet started
    PROCESSING = "processing"  # OCR in progress
    COMPLETED = "completed"  # OCR completed successfully
    FAILED = "failed"  # OCR failed


class Document(Base):
    """Document model - uploaded files for legal cases

    Attributes:
        id: Unique document identifier (UUID)
        conversation_id: Foreign key to Conversation this document belongs to
        user_id: Foreign key to User who uploaded this document
        filename: Original filename from upload
        file_type: MIME type (e.g., "application/pdf", "image/png")
        file_size: File size in bytes
        s3_key: S3 object key
            (e.g., "users/{user_id}/conversations/{conversation_id}/documents/{document_id}/filename.pdf")
        s3_url: Pre-signed or permanent URL for download
        upload_status: S3 upload status (uploading/completed/failed)
        ocr_status: OCR processing status (pending/processing/completed/failed)
        ocr_text: Extracted text from OCR (null if not processed)
        created_at: When document was uploaded
    """

    __tablename__ = "documents"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys
    conversation_id = Column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )  # For quick user document queries

    # File metadata
    filename = Column(String(500), nullable=False)  # Original filename (with extension)
    file_type = Column(String(100), nullable=False)  # MIME type (e.g., "application/pdf")
    file_size = Column(Integer, nullable=False)  # File size in bytes

    # S3 storage
    s3_key = Column(String(1000), nullable=False, unique=True)  # S3 object key (must be unique)
    s3_url = Column(String(2000), nullable=False)  # Pre-signed URL or permanent URL for download

    # Upload tracking
    upload_status = Column(Enum(UploadStatus), default=UploadStatus.UPLOADING, nullable=False, index=True)

    # OCR processing
    ocr_status = Column(Enum(OCRStatus), default=OCRStatus.PENDING, nullable=False, index=True)
    ocr_text = Column(Text, nullable=True)  # Extracted text from OCR (can be very long)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="documents")
    user = relationship("User", back_populates="documents")

    # Indexes (composite indexes for common queries)
    __table_args__ = (
        Index("ix_documents_conversation_created", "conversation_id", "created_at"),  # Get documents chronologically
        Index("ix_documents_user_created", "user_id", "created_at"),  # Get user's documents by date
        Index("ix_documents_upload_status", "upload_status"),  # Track upload progress
        Index("ix_documents_ocr_status", "ocr_status"),  # Find documents needing OCR processing
    )

    def __repr__(self) -> str:
        return (
            f"<Document(id={self.id}, filename={self.filename}, "
            f"upload_status={self.upload_status}, ocr_status={self.ocr_status})>"
        )
