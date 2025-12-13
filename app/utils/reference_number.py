"""Reference Number Generator - Generate Sumii reference numbers

Format: SUM-YYYYMMDD-XXXXX
- SUM: Prefix for Sumii
- YYYYMMDD: Date (e.g., 20250127)
- XXXXX: 5-character alphanumeric suffix (derived from UUID)
"""

import string
from datetime import datetime
from uuid import UUID


def generate_sumii_reference_number(summary_id: UUID) -> str:
    """Generate Sumii reference number from summary UUID

    Format: SUM-YYYYMMDD-XXXXX
    - SUM: Prefix for Sumii
    - YYYYMMDD: Current date (e.g., 20250127)
    - XXXXX: 5-character alphanumeric suffix derived from UUID

    Args:
        summary_id: Summary UUID

    Returns:
        str: Reference number (e.g., "SUM-20250127-ABC12")

    Example:
        >>> summary_id = UUID("123e4567-e89b-12d3-a456-426614174000")
        >>> generate_sumii_reference_number(summary_id)
        "SUM-20250127-A3F2K"
    """
    # Get current date
    today = datetime.now()
    date_str = today.strftime("%Y%m%d")

    # Generate 5-character suffix from UUID
    # Use first 5 characters of UUID hex, convert to uppercase alphanumeric
    uuid_hex = summary_id.hex.upper()
    # Take first 10 hex chars and convert to base36-like encoding
    # Use only alphanumeric (0-9, A-Z)
    suffix = ""
    for i in range(0, min(10, len(uuid_hex)), 2):
        # Take 2 hex chars, convert to int, map to alphanumeric
        hex_pair = uuid_hex[i : i + 2]
        value = int(hex_pair, 16)
        # Map to 0-9, A-Z (36 chars total)
        char = string.ascii_uppercase[value % 26] if (value % 2 == 0) else str(value % 10)
        suffix += char

    # Ensure exactly 5 characters
    suffix = suffix[:5].ljust(5, "0")

    return f"SUM-{date_str}-{suffix}"
