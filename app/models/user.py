"""User Model - Store user accounts for authentication

Users can have multiple conversations, summaries, and documents.

Uses fastapi-users SQLAlchemyBaseUserTableUUID which provides:
- id (UUID)
- email (unique, indexed)
- hashed_password
- is_active (bool, default True)
- is_superuser (bool, default False)
- is_verified (bool, default False)
- created_at (datetime)
- updated_at (datetime)
"""

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """User model for authentication

    Inherits from SQLAlchemyBaseUserTableUUID which provides:
    - id, email, hashed_password, is_active, is_superuser, is_verified, created_at, updated_at

    Custom fields for Sumii:
        language: User's preferred language (de, en) - defaults to "de"
        push_token: Expo push notification token (for mobile app)
        timezone: User's timezone (e.g., "Europe/Berlin")
        latitude: User's latitude for location-based lawyer search (optional)
        longitude: User's longitude for location-based lawyer search (optional)
    """

    __tablename__ = "users"

    # Custom fields for Sumii mobile app
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Display name (like Claude's nickname)
    language: Mapped[str | None] = mapped_column(
        String, nullable=True, default="de"
    )  # User's preferred language (de, en)
    push_token: Mapped[str | None] = mapped_column(String, nullable=True)  # Expo push notification token
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)  # User's timezone (e.g., "Europe/Berlin")

    # Location fields (for lawyer search)
    latitude: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # User's latitude (stored as string for precision, e.g., "52.5200")
    longitude: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # User's longitude (stored as string for precision, e.g., "13.4050")

    # Personal details (for Anspruchsteller section in legal summaries)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Vorname
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Nachname
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Telefonnummer
    address_street: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Straße und Hausnummer
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Stadt
    address_postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # PLZ

    # Legal insurance details (for Rechtsschutzversicherung section)
    legal_insurance: Mapped[bool | None] = mapped_column(nullable=True)  # Rechtsschutzversicherung (ja/nein)
    insurance_company: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Versicherungsgesellschaft
    insurance_number: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Versicherungsnummer

    # Relationships
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(  # noqa: F821
        "OAuthAccount", lazy="joined", cascade="all, delete-orphan"
    )
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", cascade="all, delete-orphan")
    lawyer_connections = relationship("LawyerConnection", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
