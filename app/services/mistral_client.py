"""Mistral AI Client Factory

Centralized factory for creating Mistral clients with optimized timeout settings.
This resolves SSL ReadError and stream timeout issues caused by short default httpx timeouts.

Reference: https://github.com/mistralai/client-python/issues/70#issuecomment-2275227696
See also: https://www.python-httpx.org/advanced/timeouts/
"""

import os

import httpx
from mistralai import Mistral

from app.config import settings

# Configurable timeout for AI streaming (can be adjusted via env var)
# Default: 120s read timeout for Magistral thinking phases
MISTRAL_READ_TIMEOUT = float(os.getenv("MISTRAL_READ_TIMEOUT", "120.0"))

# Optimized timeout configuration for AI streaming
# Reference: https://www.python-httpx.org/advanced/timeouts/
MISTRAL_TIMEOUT = httpx.Timeout(
    connect=10.0,  # Max time to establish connection
    read=MISTRAL_READ_TIMEOUT,  # Max time to wait for response data (critical for streaming!)
    write=30.0,  # Max time to send request data
    pool=10.0,  # Max time to wait for connection from pool
)


def get_mistral_client() -> Mistral:
    """Get Mistral client with optimized timeout settings for streaming.

    The default httpx timeout is 5 seconds which is too short for AI streaming
    responses, especially during Magistral's "thinking" phase.

    Returns:
        Mistral: Client configured with 120s read timeout for stable streaming.
    """
    return Mistral(
        api_key=settings.MISTRAL_API_KEY,
        client=httpx.Client(timeout=MISTRAL_TIMEOUT),
    )


def get_mistral_async_client() -> Mistral:
    """Get async Mistral client with optimized timeout settings.

    Use this for async streaming operations (websocket, etc).

    Returns:
        Mistral: Async client configured with 120s read timeout.
    """
    return Mistral(
        api_key=settings.MISTRAL_API_KEY,
        async_client=httpx.AsyncClient(timeout=MISTRAL_TIMEOUT),
    )
