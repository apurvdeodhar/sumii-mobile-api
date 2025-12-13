"""
Configuration Settings
Loads from .env file
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # Database (using asyncpg driver for async SQLAlchemy)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sumii_dev"

    # Mistral AI
    MISTRAL_API_KEY: str
    MISTRAL_ORG_ID: str  # Required for library sharing with agents
    MISTRAL_LIBRARY_ID: str  # Document library with BGB sections, court cases, templates

    # JWT Authentication
    SECRET_KEY: str = "development-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # OAuth Providers (optional for MVP)
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    APPLE_CLIENT_ID: str | None = None
    APPLE_TEAM_ID: str | None = None
    APPLE_KEY_ID: str | None = None
    APPLE_PRIVATE_KEY_PATH: str | None = None

    # AWS S3 (for PDF storage)
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION: str = "eu-central-1"
    S3_BUCKET: str = "sumii-pdfs-dev"

    # Logging Configuration
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_JSON_OUTPUT: bool = False  # Enable JSON structured logging (future: not implemented yet)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


# Global settings instance
settings = Settings()
