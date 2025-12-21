"""
User Schemas
Pydantic models for user request/response validation using fastapi-users base schemas
"""

import uuid

from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    """Schema for user response (read operations)

    Includes custom fields: language, push_token, timezone, latitude, longitude
    """

    language: str | None = None  # "de" | "en" (default: "de")
    push_token: str | None = None  # Expo push token or AWS SNS token
    timezone: str | None = None  # IANA timezone identifier (e.g., "Europe/Berlin")
    latitude: str | None = None  # User's latitude for location-based lawyer search
    longitude: str | None = None  # User's longitude for location-based lawyer search


class UserCreate(schemas.BaseUserCreate):
    """Schema for user registration request"""

    pass  # fastapi-users BaseUserCreate provides email and password fields


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for user profile update request"""

    language: str | None = None
    push_token: str | None = None
    timezone: str | None = None
    latitude: str | None = None
    longitude: str | None = None
