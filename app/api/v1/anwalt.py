"""Anwalt API Endpoints - Lawyer search and connection

This module provides endpoints for:
- Searching lawyers in sumii-anwalt directory (GET /api/v1/anwalt/search)
- Connecting user to lawyer (POST /api/v1/anwalt/connect)
- Auto-matching user to closest lawyer (POST /api/v1/anwalt/auto-match)
- Listing user's lawyer connections (GET /api/v1/anwalt/connections)
"""

import logging
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, LawyerConnection, Summary, User
from app.models.document import Document, UploadStatus
from app.models.lawyer_connection import ConnectionStatus
from app.schemas.lawyer_connection import (
    AutoMatchLawyerInfo,
    AutoMatchRequest,
    AutoMatchResponse,
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
    language: str = Query(..., description="Language code (de or en)", pattern="^(de|en)$"),
    legal_area: str | None = Query(None, description="Legal specialization filter (e.g., Mietrecht)"),
    lat: float | None = Query(None, description="Latitude for location-based search"),
    lng: float | None = Query(None, description="Longitude for location-based search"),
    radius: float = Query(50.0, description="Search radius in km (default: 50)"),
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


@lru_cache(maxsize=128)
def _geocode_plz(plz: str) -> tuple[float, float] | None:
    """Geocode a German PLZ (postal code) to coordinates via OpenStreetMap Nominatim.

    Results are cached in-memory — PLZ rarely changes.
    Returns (latitude, longitude) or None if geocoding fails.
    """
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="sumii-mobile-api", timeout=5)
        location = geolocator.geocode(f"{plz}, Deutschland")
        if location:
            logger.info(f"Geocoded PLZ {plz} → ({location.latitude}, {location.longitude})")
            return (location.latitude, location.longitude)
        logger.warning(f"Geocoding returned no results for PLZ {plz}")
        return None
    except Exception as e:
        logger.error(f"Geocoding failed for PLZ {plz}: {e}")
        return None


@router.post(
    "/auto-match",
    response_model=AutoMatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-match user to closest lawyer",
)
async def auto_match_lawyer(
    request: AutoMatchRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    anwalt_service: Annotated[AnwaltService, Depends(get_anwalt_service)],
) -> AutoMatchResponse:
    """Auto-match user's summary to the closest available lawyer.

    1. Validates summary ownership
    2. Geocodes PLZ if coordinates not provided
    3. Searches for the closest lawyer (100km radius)
    4. Creates LawyerConnection + case handoff
    5. Returns matched lawyer info

    Args:
        request: Auto-match request with summary_id, optional PLZ/coordinates
        current_user: Authenticated user
        db: Database session
        anwalt_service: Anwalt service for API calls

    Returns:
        AutoMatchResponse with connection_id and matched lawyer info

    Raises:
        404: Summary not found
        403: User doesn't own the summary
        400: No location provided (neither PLZ nor coordinates)
        404: No lawyers found nearby
        400: Connection already exists for this conversation
    """
    # 1. Validate summary exists and user owns it
    summary_result = await db.execute(select(Summary).where(Summary.id == request.summary_id))
    summary = summary_result.scalar_one_or_none()

    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    # Get conversation to check ownership
    conversation_result = await db.execute(select(Conversation).where(Conversation.id == summary.conversation_id))
    conversation = conversation_result.scalar_one_or_none()

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this summary")

    # 2. Check if connection already exists for this conversation
    existing_result = await db.execute(
        select(LawyerConnection).where(LawyerConnection.conversation_id == summary.conversation_id)
    )
    existing_connection = existing_result.scalar_one_or_none()

    if existing_connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A lawyer connection already exists for this conversation",
        )

    # 3. Resolve coordinates
    lat = request.lat
    lng = request.lng

    if lat is None or lng is None:
        # Try geocoding PLZ
        if request.plz:
            coords = _geocode_plz(request.plz)
            if coords:
                lat, lng = coords
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not geocode PLZ {request.plz}. Please provide device coordinates.",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location required: provide either PLZ or device coordinates (lat/lng).",
            )

    # 4. Search for the closest lawyer (100km radius)
    try:
        lawyers = await anwalt_service.search_lawyers(
            language="de",
            legal_area=request.legal_area,
            latitude=lat,
            longitude=lng,
            radius_km=100.0,
        )
    except Exception as e:
        logger.error(f"Failed to search lawyers for auto-match: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search for lawyers. Please try again.",
        )

    if not lawyers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Anwalt in der Nähe gefunden. Bitte versuche es mit einer anderen PLZ.",
        )

    # Pick the closest lawyer (first result — search_lawyers returns sorted by distance)
    closest_lawyer = lawyers[0]
    lawyer_id = closest_lawyer.get("id")
    lawyer_name = closest_lawyer.get("full_name")
    lawyer_firm = closest_lawyer.get("firm_name")

    # 5. Create LawyerConnection record
    connection = LawyerConnection(
        user_id=current_user.id,
        conversation_id=summary.conversation_id,
        summary_id=summary.id,
        lawyer_id=lawyer_id,
        lawyer_name=lawyer_name,
        lawyer_firm=lawyer_firm,
        status=ConnectionStatus.PENDING.value,
    )

    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    # 6. Hand off case to sumii-anwalt backend
    if summary.pdf_s3_key:
        try:
            from app.services.storage_service import StorageService

            storage_service = StorageService()

            # Generate presigned URL for summary PDF
            pdf_url = storage_service.generate_presigned_url(
                s3_key=str(summary.pdf_s3_key),
                expiration_days=7,
            )

            # Query completed documents for this conversation
            doc_result = await db.execute(
                select(Document)
                .where(Document.conversation_id == summary.conversation_id)
                .where(Document.upload_status == UploadStatus.COMPLETED)
                .order_by(Document.created_at)
            )
            documents = doc_result.scalars().all()

            # Generate presigned URLs for documents
            document_urls: list[dict[str, str]] | None = None
            if documents:
                document_urls = [
                    {
                        "filename": doc.filename,
                        "url": storage_service.generate_presigned_url(s3_key=str(doc.s3_key), expiration_days=7),
                        "file_type": doc.file_type,
                    }
                    for doc in documents
                ]

            # User location
            user_location = None
            if lat and lng:
                user_location = {"lat": lat, "lng": lng}

            # Hand off case
            handoff_response = await anwalt_service.handoff_case(
                user_id=str(current_user.id),
                summary_id=str(summary.id),
                summary_pdf_url=pdf_url,
                lawyer_id=lawyer_id,
                legal_area=request.legal_area
                or (conversation.legal_area.value if conversation.legal_area else "Other"),
                urgency=conversation.urgency.value if conversation.urgency else "weeks",
                user_location=user_location,
                document_urls=document_urls,
                conversation_id=str(summary.conversation_id),
            )

            # Update connection with case_id from sumii-anwalt
            if "case_id" in handoff_response:
                connection.case_id = handoff_response["case_id"]
                await db.commit()
                await db.refresh(connection)

            logger.info(
                f"Auto-match handoff successful: lawyer={lawyer_name} ({lawyer_id}), "
                f"case_id={handoff_response.get('case_id')}, connection_id={connection.id}"
            )

        except Exception as e:
            logger.error(f"Auto-match case handoff failed: {e}", exc_info=True)
            # Connection is still created — handoff can be retried manually

    # 7. Build response
    lawyer_info = AutoMatchLawyerInfo(
        id=lawyer_id,
        full_name=lawyer_name,
        firm=closest_lawyer.get("firm_name"),
        specialization=closest_lawyer.get("specialization"),
        distance_km=closest_lawyer.get("distance"),
        tier=closest_lawyer.get("tier"),
        location=closest_lawyer.get("location"),
    )

    return AutoMatchResponse(
        connection_id=connection.id,
        lawyer=lawyer_info,
        status=connection.status,
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
    lawyer_firm: str | None = None
    try:
        lawyer_profile = await anwalt_service.get_lawyer_profile(connection_data.lawyer_id)
        if not lawyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lawyer {connection_data.lawyer_id} not found",
            )
        lawyer_name = lawyer_profile.get("full_name")
        lawyer_firm = lawyer_profile.get("firm_name")
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
        lawyer_firm=lawyer_firm,
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

            storage_service = StorageService()

            # Generate presigned URL for summary PDF
            pdf_url = storage_service.generate_presigned_url(
                s3_key=str(summary.pdf_s3_key),
                expiration_days=7,
            )

            # Query completed documents for this conversation
            doc_result = await db.execute(
                select(Document)
                .where(Document.conversation_id == connection_data.conversation_id)
                .where(Document.upload_status == UploadStatus.COMPLETED)
                .order_by(Document.created_at)
            )
            documents = doc_result.scalars().all()

            # Generate fresh presigned URLs for each document
            document_urls: list[dict[str, str]] | None = None
            if documents:
                document_urls = []
                for doc in documents:
                    doc_url = storage_service.generate_presigned_url(
                        s3_key=str(doc.s3_key),
                        expiration_days=7,
                    )
                    document_urls.append(
                        {
                            "filename": doc.filename,
                            "url": doc_url,
                            "file_type": doc.file_type,
                        }
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
                document_urls=document_urls,
                conversation_id=str(connection_data.conversation_id),
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
    "/connections/conversation/{conversation_id}",
    response_model=LawyerConnectionResponse | None,
    summary="Get connection for a conversation",
)
async def get_connection_by_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerConnectionResponse | None:
    """Get the lawyer connection for a specific conversation, if one exists.

    Used by the mobile app to check if a summary has already been sent to a lawyer
    (to show the completed/disabled state on SlideToSend).

    Args:
        conversation_id: Conversation UUID
        current_user: Authenticated user
        db: Database session

    Returns:
        LawyerConnectionResponse if connection exists, null otherwise
    """
    result = await db.execute(
        select(LawyerConnection).where(
            LawyerConnection.conversation_id == conversation_id,
            LawyerConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return None

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
