"""Summary Endpoints - Generate and retrieve legal summaries

This module provides endpoints for:
- Generating summaries from conversations (POST /api/v1/summaries)
- Retrieving summaries (GET /api/v1/summaries/*)
- Getting PDF download URLs (GET /api/v1/summaries/{id}/pdf)
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Conversation, Summary, User
from app.models.conversation import CaseStrength, LegalArea, Urgency
from app.schemas.summary import SummaryCreate, SummaryResponse
from app.services.agents import MistralAgentsService, get_mistral_agents_service

# PDFService imported lazily to avoid WeasyPrint system dependencies in tests
from app.services.s3_service import S3Service, get_s3_service
from app.services.summary_service import get_summary_service
from app.utils.reference_number import generate_sumii_reference_number
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/summaries",
    response_model=SummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate summary for a conversation",
)
async def create_summary(
    summary_data: SummaryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    agents_service: Annotated[MistralAgentsService, Depends(get_mistral_agents_service)],
    s3_service: Annotated[S3Service, Depends(get_s3_service)],
) -> SummaryResponse:
    """Generate a legal summary for a conversation

    This endpoint:
    1. Verifies conversation exists and user owns it
    2. Checks if summary already exists (returns existing if found)
    3. Calls Summary Agent to generate markdown
    4. Converts markdown to PDF
    5. Uploads both to S3
    6. Saves summary to database

    Args:
        summary_data: Request body with conversation_id
        current_user: Authenticated user
        db: Database session
        agents_service: Mistral agents service
        s3_service: S3 service for file uploads

    Returns:
        SummaryResponse with PDF URL and metadata

    Raises:
        404: Conversation not found
        403: User doesn't own conversation
        500: Summary generation failed
    """
    # Get conversation with messages
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == summary_data.conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {summary_data.conversation_id} not found",
        )

    # Verify user owns conversation
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this conversation",
        )

    # Check if summary already exists
    existing_summary_result = await db.execute(
        select(Summary).where(Summary.conversation_id == summary_data.conversation_id)
    )
    existing_summary = existing_summary_result.scalar_one_or_none()

    if existing_summary:
        logger.info(f"Summary already exists for conversation {summary_data.conversation_id}")
        # Return existing summary (convert to response format)
        return _summary_to_response(existing_summary, s3_service)

    # Generate summary using Summary Agent
    try:
        summary_service = get_summary_service(agents_service)
        markdown_content, metadata = await summary_service.generate_summary(conversation, db)

        # Create summary record (will get ID after commit)
        summary = Summary(
            conversation_id=conversation.id,
            user_id=current_user.id,
            markdown_content=markdown_content,
            legal_area=LegalArea(
                metadata.get("legal_area", conversation.legal_area.value if conversation.legal_area else "Mietrecht")
            ),
            case_strength=CaseStrength(
                metadata.get(
                    "case_strength", conversation.case_strength.value if conversation.case_strength else "medium"
                )
            ),
            urgency=Urgency(metadata.get("urgency", conversation.urgency.value if conversation.urgency else "weeks")),
            pdf_s3_key="",  # Will be set after upload
            pdf_url="",  # Will be set after upload
        )

        db.add(summary)
        await db.flush()  # Get summary.id without committing

        # Generate reference number
        reference_number = generate_sumii_reference_number(summary.id)
        summary.reference_number = reference_number

        # Convert markdown to PDF (lazy import to avoid WeasyPrint dependencies in tests)
        from app.services.pdf_service import PDFService

        pdf_service = PDFService()
        pdf_bytes = pdf_service.markdown_to_pdf(markdown_content, reference_number)

        # Upload markdown to S3
        markdown_bytes = markdown_content.encode("utf-8")
        markdown_s3_key, _ = s3_service.upload_summary(
            file_content=markdown_bytes,
            reference_number=reference_number,
            file_extension="md",
            content_type="text/markdown",
        )
        summary.markdown_s3_key = markdown_s3_key

        # Upload PDF to S3
        pdf_s3_key, pdf_url = s3_service.upload_summary(
            file_content=pdf_bytes,
            reference_number=reference_number,
            file_extension="pdf",
            content_type="application/pdf",
        )
        summary.pdf_s3_key = pdf_s3_key
        summary.pdf_url = pdf_url

        # Update conversation status
        conversation.summary_generated = True
        if conversation.status.value == "active":
            from app.models.conversation import ConversationStatus

            conversation.status = ConversationStatus.COMPLETED

        await db.commit()
        await db.refresh(summary)

        logger.info(f"Summary generated successfully: {summary.id} ({reference_number})")

        return _summary_to_response(summary, s3_service)

    except Exception as e:
        logger.error(f"Failed to generate summary: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summary generation failed: {str(e)}",
        ) from e


@router.get(
    "/summaries/conversation/{conversation_id}",
    response_model=SummaryResponse,
    summary="Get summary by conversation ID",
)
async def get_summary_by_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    s3_service: Annotated[S3Service, Depends(get_s3_service)],
) -> SummaryResponse:
    """Get summary for a specific conversation

    Args:
        conversation_id: UUID of the conversation
        current_user: Authenticated user
        db: Database session
        s3_service: S3 service for generating pre-signed URLs

    Returns:
        SummaryResponse with PDF URL

    Raises:
        404: Summary not found
        403: User doesn't own conversation
    """
    # Get conversation to verify ownership
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this conversation",
        )

    # Get summary
    summary_result = await db.execute(select(Summary).where(Summary.conversation_id == conversation_id))
    summary = summary_result.scalar_one_or_none()

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Summary not found for conversation {conversation_id}",
        )

    return _summary_to_response(summary, s3_service)


@router.get(
    "/summaries",
    response_model=list[SummaryResponse],
    summary="List all summaries for authenticated user",
)
async def list_summaries(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    s3_service: Annotated[S3Service, Depends(get_s3_service)],
) -> list[SummaryResponse]:
    """List all summaries for the authenticated user

    Returns summaries ordered by creation date (newest first)

    Args:
        current_user: Authenticated user
        db: Database session
        s3_service: S3 service for generating pre-signed URLs

    Returns:
        List of SummaryResponse
    """
    result = await db.execute(
        select(Summary).where(Summary.user_id == current_user.id).order_by(Summary.created_at.desc())
    )
    summaries = result.scalars().all()

    return [_summary_to_response(summary, s3_service) for summary in summaries]


@router.get(
    "/summaries/{summary_id}/pdf",
    summary="Get pre-signed PDF download URL",
)
async def get_summary_pdf_url(
    summary_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    s3_service: Annotated[S3Service, Depends(get_s3_service)],
) -> dict[str, str]:
    """Get pre-signed S3 URL for PDF download

    Generates a new pre-signed URL (expires in 7 days) for downloading the summary PDF.

    Args:
        summary_id: UUID of the summary
        current_user: Authenticated user
        db: Database session
        s3_service: S3 service for generating pre-signed URLs

    Returns:
        Dict with "pdf_url" key

    Raises:
        404: Summary not found
        403: User doesn't own summary
    """
    result = await db.execute(select(Summary).where(Summary.id == summary_id))
    summary = result.scalar_one_or_none()

    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Summary {summary_id} not found",
        )

    if summary.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this summary",
        )

    # Generate new pre-signed URL (expires in 7 days)
    pdf_url = s3_service.generate_presigned_url(summary.pdf_s3_key, expiration_days=7)

    return {"pdf_url": pdf_url}


def _summary_to_response(summary: Summary, s3_service: S3Service) -> SummaryResponse:
    """Convert Summary model to SummaryResponse schema

    Args:
        summary: Summary model instance
        s3_service: S3 service for generating pre-signed URLs

    Returns:
        SummaryResponse instance
    """
    # Ensure reference_number exists (for older summaries)
    if not summary.reference_number:
        summary.reference_number = generate_sumii_reference_number(summary.id)

    # Ensure markdown_s3_key exists (for older summaries)
    if not summary.markdown_s3_key and summary.reference_number:
        summary.markdown_s3_key = f"summaries/{summary.reference_number}.md"

    # Generate fresh pre-signed URL if needed
    pdf_url = summary.pdf_url
    if not pdf_url or not pdf_url.startswith("http"):
        pdf_url = s3_service.generate_presigned_url(summary.pdf_s3_key, expiration_days=7)

    return SummaryResponse(
        id=summary.id,
        conversation_id=summary.conversation_id,
        user_id=summary.user_id,
        reference_number=summary.reference_number or generate_sumii_reference_number(summary.id),
        markdown_s3_key=summary.markdown_s3_key or f"summaries/{summary.reference_number}.md",
        pdf_s3_key=summary.pdf_s3_key,
        pdf_url=pdf_url,
        legal_area=summary.legal_area,
        case_strength=summary.case_strength,
        urgency=summary.urgency,
        created_at=summary.created_at,
    )
