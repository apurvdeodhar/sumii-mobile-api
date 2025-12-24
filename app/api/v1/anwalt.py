"""Anwalt API Endpoints - Lawyer search and connection

This module provides endpoints for:
- Searching lawyers in sumii-anwalt directory (GET /api/v1/anwalt/search)
- Connecting user to lawyer (POST /api/v1/anwalt/connect)
- Listing user's lawyer connections (GET /api/v1/anwalt/connections)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, LawyerConnection, Summary, User
from app.models.lawyer_connection import ConnectionStatus
from app.schemas.lawyer_connection import (
    LawyerConnectionCreate,
    LawyerConnectionListResponse,
    LawyerConnectionResponse,
)
from app.services.anwalt_service import AnwaltService, get_anwalt_service
from app.users import current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/anwalt", tags=["anwalt"])


@router.get("/search")
async def search_lawyers(
    current_user: Annotated[User, Depends(current_active_user)],
    anwalt_service: Annotated[AnwaltService, Depends(get_anwalt_service)],
    language: str = Query(..., description="Language code (de or en)", regex="^(de|en)$"),
    legal_area: str | None = Query(None, description="Legal specialization filter (e.g., Mietrecht)"),
    lat: float | None = Query(None, description="Latitude for location-based search"),
    lng: float | None = Query(None, description="Longitude for location-based search"),
    radius: float = Query(10.0, description="Search radius in km (default: 10)"),
) -> list[dict]:
    """Search for lawyers in sumii-anwalt directory

    Calls the sumii-anwalt backend to search for lawyers matching the criteria.
    Location parameters are passed through to sumii-anwalt for location-based search.

    Args:
        language: Language code (required: "de" or "en")
        legal_area: Legal specialization filter (optional)
        lat: Latitude for location-based search (optional)
        lng: Longitude for location-based search (optional)
        radius: Search radius in km (default: 10.0)
        current_user: Authenticated user (for logging)
        anwalt_service: Anwalt service for API calls

    Returns:
        List of lawyer profiles with fields:
        - id: Lawyer ID (integer)
        - full_name: Lawyer's full name
        - bar_id: Bar association ID
        - specialization: Legal specialization
        - location: Location string
        - languages: Comma-separated languages
        - distance: Distance in km (if lat/lng provided)

    Raises:
        400: Invalid language code
        500: Failed to search lawyers
    """
    try:
        lawyers = await anwalt_service.search_lawyers(
            language=language,
            legal_area=legal_area,
            latitude=lat,
            longitude=lng,
            radius_km=radius,
        )
        return lawyers
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search lawyers: {str(e)}",
        )


@router.post(
    "/connect",
    response_model=LawyerConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Connect user to lawyer",
)
async def connect_to_lawyer(
    connection_data: LawyerConnectionCreate,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    anwalt_service: Annotated[AnwaltService, Depends(get_anwalt_service)],
) -> LawyerConnectionResponse:
    """Connect user's conversation to a lawyer

    Creates a connection record linking the user's conversation/summary to a lawyer.
    This initiates the process of sending the case to the lawyer via sumii-anwalt.

    Args:
        connection_data: Connection request (conversation_id, lawyer_id, optional message)
        current_user: Authenticated user
        db: Database session
        anwalt_service: Anwalt service for validation

    Returns:
        LawyerConnectionResponse with connection details

    Raises:
        404: Conversation not found
        403: User doesn't own conversation
        404: Lawyer not found in sumii-anwalt
        400: Connection already exists
    """
    # Verify conversation exists and user owns it
    conversation_result = await db.execute(
        select(Conversation).where(Conversation.id == connection_data.conversation_id)
    )
    conversation = conversation_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {connection_data.conversation_id} not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to connect this conversation",
        )

    # Verify lawyer exists in sumii-anwalt
    try:
        lawyer_profile = await anwalt_service.get_lawyer_profile(connection_data.lawyer_id)
        if not lawyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lawyer {connection_data.lawyer_id} not found",
            )
        lawyer_name = lawyer_profile.get("full_name")
    except HTTPException:
        # Re-raise HTTP exceptions (like 404) as-is
        raise
    except Exception as e:
        # Wrap other exceptions as 500 errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify lawyer: {str(e)}",
        )

    # Check if connection already exists for this conversation
    existing_result = await db.execute(
        select(LawyerConnection).where(
            LawyerConnection.conversation_id == connection_data.conversation_id,
            LawyerConnection.lawyer_id == connection_data.lawyer_id,
        )
    )
    existing_connection = existing_result.scalar_one_or_none()

    if existing_connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection already exists for this conversation and lawyer",
        )

    # Get summary for this conversation if it exists
    summary_result = await db.execute(select(Summary).where(Summary.conversation_id == connection_data.conversation_id))
    summary = summary_result.scalar_one_or_none()

    # Create connection record first
    connection = LawyerConnection(
        user_id=current_user.id,
        conversation_id=connection_data.conversation_id,
        summary_id=summary.id if summary else None,
        lawyer_id=connection_data.lawyer_id,
        lawyer_name=lawyer_name,
        user_message=connection_data.user_message,
        status=ConnectionStatus.PENDING.value,
    )

    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    # Hand off case to sumii-anwalt backend if summary exists
    if summary:
        try:
            from app.services.storage_service import StorageService

            # Get storage service to generate pre-signed URL
            storage_service = StorageService()

            # Get pre-signed URL for summary PDF (7 days expiry)
            pdf_url = storage_service.generate_presigned_url(
                s3_key=str(summary.pdf_s3_key),
                expiration_days=7,
            )

            # Get user location if available
            user_location = None
            if current_user.latitude and current_user.longitude:
                user_location = {
                    "lat": float(current_user.latitude),
                    "lng": float(current_user.longitude),
                }

            # Hand off case to sumii-anwalt
            handoff_response = await anwalt_service.handoff_case(
                user_id=str(current_user.id),
                summary_id=str(summary.id),
                summary_pdf_url=pdf_url,
                lawyer_id=connection_data.lawyer_id,
                legal_area=conversation.legal_area.value if conversation.legal_area else "Other",
                urgency=conversation.urgency.value if conversation.urgency else "weeks",
                user_location=user_location,
            )

            # Update connection with case_id from sumii-anwalt
            if "case_id" in handoff_response:
                connection.case_id = handoff_response["case_id"]
                await db.commit()
                await db.refresh(connection)

            logger.info(
                f"Case handoff successful: case_id={handoff_response.get('case_id')}, connection_id={connection.id}"
            )

        except Exception as e:
            logger.error(f"Failed to hand off case to sumii-anwalt: {e}", exc_info=True)
            # Don't fail the connection creation if handoff fails
            # Connection is still created, but status remains PENDING
            # This allows manual retry later

    return LawyerConnectionResponse.model_validate(connection)


@router.get(
    "/connections",
    response_model=LawyerConnectionListResponse,
    summary="List user's lawyer connections",
)
async def list_connections(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: ConnectionStatus | None = Query(None, description="Filter by connection status"),
) -> LawyerConnectionListResponse:
    """List all lawyer connections for the authenticated user

    Args:
        current_user: Authenticated user
        db: Database session
        status_filter: Optional filter by connection status

    Returns:
        LawyerConnectionListResponse with list of connections
    """
    query = select(LawyerConnection).where(LawyerConnection.user_id == current_user.id)

    if status_filter:
        query = query.where(LawyerConnection.status == status_filter.value)

    query = query.order_by(LawyerConnection.created_at.desc())

    result = await db.execute(query)
    connections = result.scalars().all()

    return LawyerConnectionListResponse(
        connections=[LawyerConnectionResponse.model_validate(conn) for conn in connections],
        total=len(connections),
    )
