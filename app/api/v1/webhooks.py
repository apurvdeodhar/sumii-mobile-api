"""Webhook Endpoints - Receive events from external services (sumii-anwalt)

Webhooks are called by external services to notify sumii-mobile-api of events.
These endpoints use API key authentication (X-API-Key header).
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import LawyerConnection, Notification, User
from app.models.lawyer_connection import ConnectionStatus
from app.models.notification import NotificationType
from app.schemas.webhook import LawyerResponseWebhookRequest, LawyerResponseWebhookResponse
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify API key for webhook authentication

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        API key if valid

    Raises:
        401: If API key is invalid or not configured
    """
    if not settings.ANWALT_API_KEY:
        logger.warning("ANWALT_API_KEY not configured - webhook authentication disabled (development mode)")
        # In development, allow any key if not configured
        return x_api_key

    if x_api_key != settings.ANWALT_API_KEY:
        logger.warning(f"Invalid API key provided: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return x_api_key


@router.post(
    "/lawyer-response",
    response_model=LawyerResponseWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive lawyer response webhook from sumii-anwalt",
)
async def lawyer_response_webhook(
    webhook_data: LawyerResponseWebhookRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LawyerResponseWebhookResponse:
    """Webhook endpoint for lawyer responses from sumii-anwalt

    When a lawyer responds to a case in sumii-anwalt, this endpoint is called
    to create a notification and send an email to the user.

    Args:
        webhook_data: Webhook payload with lawyer response details
        api_key: Verified API key (from X-API-Key header)
        db: Database session

    Returns:
        LawyerResponseWebhookResponse with status and details

    Raises:
        404: User or conversation not found
        400: Invalid request data
    """
    logger.info(
        f"Received lawyer response webhook: case_id={webhook_data.case_id}, "
        f"conversation_id={webhook_data.conversation_id}, lawyer_id={webhook_data.lawyer_id}"
    )

    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == webhook_data.user_id))
    user = user_result.unique().scalar_one_or_none()
    if not user:
        logger.error(f"User not found: {webhook_data.user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {webhook_data.user_id} not found",
        )

    # Verify conversation exists (optional check, but good for validation)
    from app.models import Conversation

    conversation_result = await db.execute(select(Conversation).where(Conversation.id == webhook_data.conversation_id))
    conversation = conversation_result.scalar_one_or_none()
    if not conversation:
        logger.error(f"Conversation not found: {webhook_data.conversation_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {webhook_data.conversation_id} not found",
        )

    # Verify user owns the conversation
    if conversation.user_id != webhook_data.user_id:
        logger.error(f"User {webhook_data.user_id} does not own conversation {webhook_data.conversation_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not own this conversation",
        )

    # Update lawyer connection record if it exists
    connection_result = await db.execute(
        select(LawyerConnection).where(
            LawyerConnection.conversation_id == webhook_data.conversation_id,
            LawyerConnection.lawyer_id == webhook_data.lawyer_id,
        )
    )
    connection = connection_result.scalar_one_or_none()

    if connection:
        # Update connection status to accepted and set response timestamp
        connection.status = ConnectionStatus.ACCEPTED.value
        connection.lawyer_response_at = webhook_data.response_timestamp
        connection.lawyer_name = webhook_data.lawyer_name  # Update cached name
        if connection.case_id is None:
            connection.case_id = webhook_data.case_id
        await db.commit()
        logger.info(f"Updated lawyer connection {connection.id} with response")
    else:
        logger.warning(
            f"No lawyer connection found for conversation {webhook_data.conversation_id} "
            f"and lawyer {webhook_data.lawyer_id} - creating notification anyway"
        )

    # Create notification
    notification = Notification(
        user_id=webhook_data.user_id,
        type=NotificationType.LAWYER_RESPONSE.value,
        title="Anwalt hat geantwortet",
        message=f"Ihr Anwalt {webhook_data.lawyer_name} hat auf Ihren Fall geantwortet.",
        data={
            "case_id": webhook_data.case_id,
            "conversation_id": str(webhook_data.conversation_id),
            "lawyer_id": webhook_data.lawyer_id,
            "lawyer_name": webhook_data.lawyer_name,
            "response_text": webhook_data.response_text,
            "response_timestamp": webhook_data.response_timestamp.isoformat(),
        },
        read=False,
    )
    db.add(notification)
    await db.flush()  # Get notification.id without committing
    await db.commit()

    logger.info(f"Created notification {notification.id} for user {webhook_data.user_id}")

    # Send email to user (non-blocking, log errors but don't fail webhook)
    email_sent = False
    try:
        email_service = EmailService()
        # Generate case summary URL (frontend URL to view the conversation/summary)
        case_summary_url = f"{settings.FRONTEND_URL}/conversations/{webhook_data.conversation_id}"
        await email_service.send_lawyer_response_email(
            user_email=user.email,
            lawyer_name=webhook_data.lawyer_name,
            case_summary_url=case_summary_url,
        )
        email_sent = True
        logger.info(f"Sent lawyer response email to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send email to {user.email}: {e}", exc_info=True)
        # Don't fail the webhook if email fails

    return LawyerResponseWebhookResponse(
        status="success",
        message=f"Notification created and email sent to user {user.email}",
        notification_id=notification.id,
        email_sent=email_sent,
    )
