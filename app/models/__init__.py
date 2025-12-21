"""Database Models

All models must be imported here for Alembic auto-detect to work.
"""

from app.models.conversation import CaseStrength, Conversation, ConversationStatus, LegalArea, Urgency
from app.models.document import Document, OCRStatus, UploadStatus
from app.models.lawyer_connection import ConnectionStatus, LawyerConnection
from app.models.message import Message, MessageRole
from app.models.notification import Notification, NotificationType
from app.models.oauth_account import OAuthAccount
from app.models.summary import Summary
from app.models.user import User

__all__ = [
    "User",
    "OAuthAccount",
    "Conversation",
    "Message",
    "Summary",
    "Document",
    "Notification",
    "LawyerConnection",
    # Enums
    "ConversationStatus",
    "LegalArea",
    "CaseStrength",
    "Urgency",
    "MessageRole",
    "OCRStatus",
    "UploadStatus",
    "NotificationType",
    "ConnectionStatus",
]
