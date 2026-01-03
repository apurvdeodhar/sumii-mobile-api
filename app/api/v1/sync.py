"""Sync API Endpoint - Mobile data synchronization

Provides delta sync for mobile clients:
- Client sends last_synced_at timestamp
- Server returns all changes since that timestamp
- Client updates local SQLite and saves server_time for next sync
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.lawyer_connection import LawyerConnection
from app.models.message import Message
from app.models.notification import Notification
from app.models.summary import Summary
from app.models.user import User
from app.schemas.conversation import ConversationResponse, MessageResponse
from app.schemas.document import DocumentResponse
from app.schemas.lawyer_connection import LawyerConnectionResponse
from app.schemas.notification import NotificationResponse
from app.schemas.summary import SummaryResponse
from app.schemas.sync import DeletedIds, SyncRequest, SyncResponse
from app.users import current_active_user

router = APIRouter()


@router.post(
    "/sync",
    response_model=SyncResponse,
    summary="Sync mobile client data",
    tags=["sync"],
)
async def sync_data(
    sync_request: SyncRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SyncResponse:
    """Synchronize data for mobile client

    - **last_synced_at**: Timestamp of last successful sync (None for full sync)
    - Returns all conversations, messages, documents, summaries, notifications, lawyer_connections
      that have been created or updated since last_synced_at
    - Returns server_time to use as last_synced_at for next sync
    """
    last_synced_at = sync_request.last_synced_at
    is_full_sync = last_synced_at is None
    server_time = datetime.utcnow()

    # If no last_synced_at, set to epoch (get everything)
    if last_synced_at is None:
        last_synced_at = datetime(1970, 1, 1)

    # Query conversations updated since last sync
    conversations_result = await db.execute(
        select(Conversation)
        .where(
            and_(
                Conversation.user_id == current_user.id,
                Conversation.updated_at > last_synced_at,
            )
        )
        .order_by(Conversation.updated_at.desc())
    )
    conversations = list(conversations_result.scalars().all())

    # Query messages - need to join with conversation to filter by user
    messages_result = await db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            and_(
                Conversation.user_id == current_user.id,
                Message.created_at > last_synced_at,
            )
        )
        .order_by(Message.created_at.desc())
    )
    messages = list(messages_result.scalars().all())

    # Query documents updated since last sync
    documents_result = await db.execute(
        select(Document)
        .where(
            and_(
                Document.user_id == current_user.id,
                Document.created_at > last_synced_at,
            )
        )
        .order_by(Document.created_at.desc())
    )
    documents = list(documents_result.scalars().all())

    # Query summaries updated since last sync
    summaries_result = await db.execute(
        select(Summary)
        .where(
            and_(
                Summary.user_id == current_user.id,
                Summary.created_at > last_synced_at,
            )
        )
        .order_by(Summary.created_at.desc())
    )
    summaries = list(summaries_result.scalars().all())

    # Query notifications updated since last sync
    notifications_result = await db.execute(
        select(Notification)
        .where(
            and_(
                Notification.user_id == current_user.id,
                or_(
                    Notification.created_at > last_synced_at,
                    Notification.read_at > last_synced_at,
                ),
            )
        )
        .order_by(Notification.created_at.desc())
    )
    notifications = list(notifications_result.scalars().all())

    # Query lawyer connections updated since last sync
    lawyer_connections_result = await db.execute(
        select(LawyerConnection)
        .where(
            and_(
                LawyerConnection.user_id == current_user.id,
                LawyerConnection.updated_at > last_synced_at,
            )
        )
        .order_by(LawyerConnection.updated_at.desc())
    )
    lawyer_connections = list(lawyer_connections_result.scalars().all())

    # TODO: Query deleted records (requires soft delete implementation)
    deleted_ids = DeletedIds()

    return SyncResponse(
        conversations=[ConversationResponse.model_validate(c) for c in conversations],
        messages=[MessageResponse.model_validate(m) for m in messages],
        documents=[DocumentResponse.model_validate(d) for d in documents],
        summaries=[SummaryResponse.model_validate(s) for s in summaries],
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        lawyer_connections=[LawyerConnectionResponse.model_validate(lc) for lc in lawyer_connections],
        deleted_ids=deleted_ids,
        server_time=server_time,
        is_full_sync=is_full_sync,
    )
