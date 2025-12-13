"""User Model - Store user accounts for authentication

Users can have multiple conversations, summaries, and documents.
"""

import uuid

from sqlalchemy import Column, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """User model for authentication

    Attributes:
        id: Unique user identifier (UUID)
        email: User's email address (unique)
        hashed_password: Bcrypt hashed password
        language: User's preferred language (de, en) - defaults to "de"
        push_token: Expo push notification token (for mobile app)
        timezone: User's timezone (e.g., "Europe/Berlin")
        created_at: When user account was created
        updated_at: When user account was last updated
    """

    __tablename__ = "users"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Authentication
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)

    # Mobile app fields
    language = Column(String, nullable=True, default="de")  # User's preferred language (de, en)
    push_token = Column(String, nullable=True)  # Expo push notification token
    timezone = Column(String, nullable=True)  # User's timezone (e.g., "Europe/Berlin")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", cascade="all, delete-orphan")
    lawyer_connections = relationship("LawyerConnection", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
