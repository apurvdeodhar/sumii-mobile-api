"""
Simple Centralized Logging Configuration

Uses Python's standard logging.basicConfig() - simple, safe, maintainable.
All configuration via environment variables in .env file.

Usage:
    # In app/main.py (one-time setup)
    from app.utils.logging_config import setup_logging
    setup_logging()

    # In any module (no changes needed!)
    import logging
    logger = logging.getLogger(__name__)
    logger.info("This works!")
"""

import logging
import sys

from app.config import settings


def _get_log_level(level_str: str) -> int:
    """Convert string log level to logging constant"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def setup_logging() -> None:
    """Configure logging from Pydantic Settings

    Simple approach using logging.basicConfig() - standard Python way.

    Reads from settings:
    - LOG_LEVEL: Global log level (default: INFO)
    - LOG_JSON_OUTPUT: Enable JSON structured logging (default: False)
    """
    # Get global log level
    root_level = _get_log_level(settings.LOG_LEVEL)

    # Simple format - clean and readable
    log_format = "%(asctime)s | %(name)-25s | %(levelname)-8s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Use Python's standard basicConfig (simple, safe, maintainable)
    logging.basicConfig(
        level=root_level,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Override any existing configuration
    )

    # Suppress noisy third-party loggers
    # SQLAlchemy - completely silent (we already set echo=False in database.py)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.CRITICAL)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.CRITICAL)
    logging.getLogger("sqlalchemy").setLevel(logging.CRITICAL)

    # Uvicorn - configure loggers
    # Note: uvicorn.error is misleading - it logs all messages, not just errors
    # We suppress uvicorn.error to WARNING to reduce noise (startup/shutdown messages)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    # Keep uvicorn.access at INFO to see HTTP requests (GET /health 200 OK, etc.)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    # Other noisy libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
