"""Push Notification Schemas - Request/Response models for push notification API"""

from pydantic import BaseModel, Field


class PushTokenRegister(BaseModel):
    """Register push token request schema"""

    push_token: str = Field(..., description="Expo push token or AWS SNS token")


class PushTokenRegisterResponse(BaseModel):
    """Push token registration response"""

    status: str = "registered"
    message: str = "Push token registered successfully"
