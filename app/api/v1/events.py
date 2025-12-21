"""SSE Events Endpoint - Server-Sent Events for notifications

This module provides SSE (Server-Sent Events) streaming for real-time notifications.
SSE is used for events/notifications only (one-way: backend → mobile app).
Chat uses WebSocket (bidirectional).

Event types:
- summary_ready - Summary generated for conversation
- lawyer_response - Lawyer responded to case
- lawyer_assigned - Lawyer accepted case
- case_updated - Case status changed
"""

import asyncio
import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Notification, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["events"])


async def get_current_user_from_token(
    token: str = Query(..., description="JWT token for authentication"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from JWT token in query parameter (for SSE compatibility)

    SSE (Server-Sent Events) doesn't easily support custom headers, so we accept
    the token as a query parameter instead of Authorization header.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode JWT token (fastapi-users format with 'sub' containing user ID)
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},  # Allow tokens without audience
        )
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = UUID(user_id_str)
    except (JWTError, ValueError) as e:
        logger.debug(f"Token validation failed: {e}")
        raise credentials_exception from e

    # Get user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.unique().scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return user


async def get_unread_notifications(user_id: UUID, db: AsyncSession) -> list[Notification]:
    """Get unread notifications for a user

    Args:
        user_id: User UUID
        db: Database session

    Returns:
        List of unread notifications ordered by creation date (newest first)
    """
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)  # noqa: E712
        .order_by(Notification.created_at.desc())
    )
    return list(result.scalars().all())


async def mark_notification_as_read(notification_id: UUID, db: AsyncSession) -> None:
    """Mark a notification as read

    Args:
        notification_id: Notification UUID
        db: Database session
    """
    from datetime import datetime, timezone

    from sqlalchemy import update

    await db.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(read=True, read_at=datetime.now(timezone.utc))
    )
    await db.commit()


@router.get("/events/subscribe")
async def subscribe_events(
    current_user: Annotated[User, Depends(get_current_user_from_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """SSE endpoint for real-time events/notifications

    Streams Server-Sent Events (SSE) for notifications like:
    - summary_ready: Summary generated for conversation
    - lawyer_response: Lawyer responded to case
    - lawyer_assigned: Lawyer accepted case
    - case_updated: Case status changed

    Args:
        token: JWT token (from query parameter for SSE compatibility)
        current_user: Authenticated user (from token)
        db: Database session

    Returns:
        StreamingResponse with text/event-stream content type

    Example SSE format:
        event: summary_ready
        data: {"type": "summary_ready", "title": "Zusammenfassung bereit", "message": "...", "data": {...}}

        event: lawyer_response
        data: {"type": "lawyer_response", "title": "Anwalt hat geantwortet", "message": "...", "data": {...}}
    """

    async def event_generator():
        """Stream events as they occur"""
        try:
            while True:
                # Check for new notifications for this user
                notifications = await get_unread_notifications(current_user.id, db)

                for notification in notifications:
                    # Build event data from notification
                    event_data = {
                        "type": notification.type,
                        "title": notification.title,
                        "message": notification.message,
                        "data": notification.data if notification.data else {},
                    }

                    # Stream event in SSE format
                    # Format: event: <event_type>\ndata: <json>\n\n
                    yield f"event: {notification.type}\n"
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # Mark notification as read after streaming
                    await mark_notification_as_read(notification.id, db)

                    logger.debug(f"Streamed SSE event: {notification.type} to user {current_user.id}")

                # Poll every second for new notifications
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info(f"SSE connection closed for user {current_user.id}")
            raise
        except Exception as e:
            logger.error(f"Error in SSE event stream for user {current_user.id}: {e}", exc_info=True)
            # Send error event before closing
            error_data = {
                "type": "error",
                "title": "Connection Error",
                "message": "An error occurred while streaming events",
                "data": {},
            }
            yield "event: error\n"
            yield f"data: {json.dumps(error_data)}\n\n"
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
