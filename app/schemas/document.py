"""Document Schemas - Request/Response models for document upload API"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import OCRStatus, UploadStatus


class DocumentUpload(BaseModel):
    """Document upload request schema (multipart/form-data)

    Used with FastAPI UploadFile:
    - file: UploadFile (binary file data)
    - conversation_id: UUID (from Form(...))
    - run_ocr: bool (from Form(False))
    """

    conversation_id: UUID = Field(..., description="Conversation ID this document belongs to")
    run_ocr: bool = Field(False, description="Whether to run OCR on this document (default: False)")


class DocumentResponse(BaseModel):
    """Document response with all fields"""

    id: UUID
    conversation_id: UUID
    user_id: UUID
    filename: str
    file_type: str
    file_size: int
    s3_key: str
    s3_url: str

    # Upload tracking
    upload_status: UploadStatus

    # OCR tracking
    ocr_status: OCRStatus
    ocr_text: Optional[str] = None

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """List of documents with total count"""

    documents: List[DocumentResponse]
    total: int
