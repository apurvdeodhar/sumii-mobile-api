"""Mistral AI Client Factory

Centralized factory for creating Mistral clients with optimized timeout settings.
This resolves SSL ReadError and stream timeout issues caused by short default httpx timeouts.

Reference: https://github.com/mistralai/client-python/issues/70#issuecomment-2275227696
See also: https://www.python-httpx.org/advanced/timeouts/
"""

import httpx
from mistralai import Mistral, RetryConfig
from mistralai.utils.retries import BackoffStrategy

from app.config import settings

# Retry configuration for transient errors (429, 5xx, connection errors)
MISTRAL_RETRY_CONFIG = RetryConfig(
    strategy="backoff",
    backoff=BackoffStrategy(
        initial_interval=1000,  # 1s initial wait
        max_interval=30000,  # 30s max wait
        exponent=1.5,  # moderate exponential growth
        max_elapsed_time=120000,  # 2min total retry window
    ),
    retry_connection_errors=True,
)

# Optimized timeout configuration for AI streaming
# Reference: https://www.python-httpx.org/advanced/timeouts/
MISTRAL_TIMEOUT = httpx.Timeout(
    connect=10.0,  # Max time to establish connection
    read=settings.MISTRAL_READ_TIMEOUT,  # Max time to wait for response data (critical for streaming!)
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
        retry_config=MISTRAL_RETRY_CONFIG,
    )


def get_mistral_async_client() -> Mistral:
    """Get async Mistral client with optimized timeout settings.

    Use this for async streaming operations (websocket, etc).

    Returns:
        Mistral: Async client configured with 120s read timeout and retry.
    """
    return Mistral(
        api_key=settings.MISTRAL_API_KEY,
        async_client=httpx.AsyncClient(timeout=MISTRAL_TIMEOUT),
        retry_config=MISTRAL_RETRY_CONFIG,
    )
