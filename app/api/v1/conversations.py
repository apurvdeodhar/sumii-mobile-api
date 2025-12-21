"""Conversation CRUD Endpoints - Manage user conversations"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessages,
)
from app.users import current_active_user

router = APIRouter()


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Create a new conversation for the authenticated user

    - **title**: Optional conversation title (auto-generated if not provided)
    - Returns the created conversation with ID
    """
    # Create conversation with auto-generated title if not provided
    title = conversation_data.title or f"Conversation {uuid4().hex[:8]}"

    conversation = Conversation(
        user_id=current_user.id,
        title=title,
        current_agent="router",  # Start with router agent
    )

    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return conversation


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List all user conversations",
)
async def list_conversations(
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Conversation]:
    """Retrieve all conversations for the authenticated user

    - Returns conversations ordered by creation date (newest first)
    - Does NOT include messages (use GET /conversations/{id} for that)
    """
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == current_user.id).order_by(Conversation.created_at.desc())
    )
    conversations = result.scalars().all()

    return list(conversations)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithMessages,
    summary="Get conversation with all messages",
)
async def get_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Retrieve a single conversation with all messages

    - **conversation_id**: UUID of the conversation
    - Returns conversation with full message history
    - Returns 404 if conversation doesn't exist
    - Returns 403 if conversation belongs to another user
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))  # Eager load messages
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Check ownership
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this conversation",
        )

    return conversation


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update conversation metadata",
)
async def update_conversation(
    conversation_id: UUID,
    conversation_data: ConversationUpdate,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Conversation:
    """Update conversation metadata

    - **conversation_id**: UUID of the conversation
    - Only provided fields will be updated
    - Returns 404 if conversation doesn't exist
    - Returns 403 if conversation belongs to another user
    """
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Check ownership
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this conversation",
        )

    # Update only provided fields
    update_data = conversation_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(conversation, field, value)

    await db.commit()
    await db.refresh(conversation)

    return conversation


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation (GDPR compliance)",
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a conversation and all associated messages

    - **conversation_id**: UUID of the conversation
    - Permanently deletes conversation and all messages (cascade delete)
    - Returns 404 if conversation doesn't exist
    - Returns 403 if conversation belongs to another user
    - Returns 204 No Content on success
    """
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Check ownership
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this conversation",
        )

    await db.delete(conversation)
    await db.commit()
