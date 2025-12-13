"""
User Schemas
Pydantic models for user request/response validation
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    """Schema for user registration request"""

    email: EmailStr
    password: str


class UserLogin(BaseModel):
    """Schema for user login request"""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response (no password!)

    Includes mobile-specific fields: language, push_token, timezone
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    language: str | None = None  # "de" | "en" (default: "de")
    push_token: str | None = None  # Expo push token or AWS SNS token
    timezone: str | None = None  # IANA timezone identifier (e.g., "Europe/Berlin")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Token(BaseModel):
    """Schema for JWT token response"""

    access_token: str
    token_type: str = "bearer"
