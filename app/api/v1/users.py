"""Users API - User profile and push notification token management

Endpoints:
- POST /users/push-token - Register push notification token
- GET /users/profile - Get current user profile
- PATCH /users/profile - Update user profile
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.users import current_active_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


# Schemas
class PushTokenRequest(BaseModel):
    """Request body for push token registration"""

    push_token: str = Field(..., description="Expo push notification token")


class PushTokenResponse(BaseModel):
    """Response for push token registration"""

    status: str = "registered"


class UserProfileResponse(BaseModel):
    """User profile response"""

    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_postal_code: str | None = None
    language: str | None = None
    timezone: str | None = None
    legal_insurance: bool | None = None
    insurance_company: str | None = None
    insurance_number: str | None = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Request body for profile update"""

    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_postal_code: str | None = None
    language: str | None = None
    timezone: str | None = None
    legal_insurance: bool | None = None
    insurance_company: str | None = None
    insurance_number: str | None = None


# Endpoints
@router.post("/push-token", response_model=PushTokenResponse)
async def register_push_token(
    data: PushTokenRequest,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PushTokenResponse:
    """Register Expo push notification token for the current user

    The mobile app should call this endpoint after obtaining a push token
    from Expo's Notifications API.

    Args:
        data: Push token request containing the Expo push token
        current_user: Authenticated user
        db: Database session

    Returns:
        Status confirmation
    """
    current_user.push_token = data.push_token
    await db.commit()
    return PushTokenResponse(status="registered")


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: Annotated[User, Depends(current_active_user)],
) -> UserProfileResponse:
    """Get current user profile

    Returns:
        User profile with all editable fields
    """
    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        address_street=current_user.address_street,
        address_city=current_user.address_city,
        address_postal_code=current_user.address_postal_code,
        language=current_user.language,
        timezone=current_user.timezone,
        legal_insurance=current_user.legal_insurance,
        insurance_company=current_user.insurance_company,
        insurance_number=current_user.insurance_number,
    )


@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileUpdate,
    current_user: Annotated[User, Depends(current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileResponse:
    """Update current user profile

    Only provided fields will be updated. Fields set to None are ignored.

    Args:
        data: Profile update request
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated user profile
    """
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return UserProfileResponse(
        id=str(current_user.id),
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        address_street=current_user.address_street,
        address_city=current_user.address_city,
        address_postal_code=current_user.address_postal_code,
        language=current_user.language,
        timezone=current_user.timezone,
        legal_insurance=current_user.legal_insurance,
        insurance_company=current_user.insurance_company,
        insurance_number=current_user.insurance_number,
    )
