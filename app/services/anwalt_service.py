"""Anwalt Service - Integration with sumii-anwalt backend

This service handles communication with the sumii-anwalt backend (lawyer-facing dashboard)
to search for lawyers and connect users with legal professionals.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class AnwaltService:
    """Service for interacting with sumii-anwalt backend API"""

    def __init__(self):
        """Initialize Anwalt service with base URL from config"""
        self.base_url = settings.ANWALT_API_BASE_URL.rstrip("/")

    async def search_lawyers(
        self,
        language: str,
        legal_area: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 10.0,
    ) -> list[dict[str, Any]]:
        """Search for lawyers in sumii-anwalt directory

        Calls the public /anwalt/profiles endpoint on sumii-anwalt backend.

        Args:
            language: Language code (required: "de" or "en")
            legal_area: Legal specialization filter (optional, e.g., "Mietrecht", "Arbeitsrecht")
            latitude: Latitude for location-based search (optional)
            longitude: Longitude for location-based search (optional)
            radius_km: Search radius in kilometers (default: 10.0)

        Returns:
            List of lawyer profile dictionaries with fields:
            - id: Lawyer ID (integer)
            - full_name: Lawyer's full name
            - bar_id: Bar association ID
            - specialization: Legal specialization
            - location: Location string
            - languages: Comma-separated languages (e.g., "de,en")
            - distance: Distance in km (if lat/lng provided, else None)

        Raises:
            httpx.HTTPError: If API request fails
            ValueError: If language is invalid
        """
        # Validate language
        if language not in ["de", "en"]:
            raise ValueError(f"Invalid language code: {language}. Must be 'de' or 'en'")

        # Build query parameters
        params: dict[str, Any] = {"lang": language}
        if legal_area:
            params["legal_area"] = legal_area
        if latitude is not None:
            params["lat"] = latitude
        if longitude is not None:
            params["lng"] = longitude
        if radius_km:
            params["radius"] = radius_km

        # Make request to sumii-anwalt backend
        url = f"{self.base_url}/anwalt/profiles"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to search lawyers in sumii-anwalt: {e}")
            raise Exception(f"Failed to search lawyers: {str(e)}") from e

    async def get_lawyer_profile(self, lawyer_id: int) -> dict[str, Any] | None:
        """Get lawyer profile by ID

        Note: This endpoint may not exist in sumii-anwalt yet.
        For now, we can search and filter by ID client-side.

        Args:
            lawyer_id: Lawyer ID from sumii-anwalt

        Returns:
            Lawyer profile dictionary or None if not found

        Raises:
            httpx.HTTPError: If API request fails
        """
        # Search all lawyers and filter by ID
        # This is inefficient but works until sumii-anwalt adds GET /anwalt/profiles/{id}
        try:
            lawyers = await self.search_lawyers(language="de")  # Default language
            for lawyer in lawyers:
                if lawyer.get("id") == lawyer_id:
                    return lawyer
            return None
        except Exception as e:
            logger.error(f"Failed to get lawyer profile {lawyer_id}: {e}")
            raise

    async def handoff_case(
        self,
        user_id: str,
        summary_id: str,
        summary_pdf_url: str,
        lawyer_id: int,
        legal_area: str,
        case_strength: str,
        urgency: str,
        user_location: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Hand off case to sumii-anwalt backend

        Creates a case in the sumii-anwalt system and assigns it to a lawyer.
        This is called after a user connects their conversation/summary to a lawyer.

        Args:
            user_id: User UUID from mobile-api
            summary_id: Summary UUID from mobile-api
            summary_pdf_url: Pre-signed S3 URL for the summary PDF
            lawyer_id: Lawyer ID from sumii-anwalt
            legal_area: Legal area (e.g., "Mietrecht", "Arbeitsrecht")
            case_strength: Case strength (e.g., "strong", "medium", "weak")
            urgency: Urgency level (e.g., "immediate", "weeks", "months")
            user_location: Optional user location dict with keys: city, lat, lng

        Returns:
            Dictionary with case_id from sumii-anwalt system

        Raises:
            httpx.HTTPError: If API request fails
            Exception: If handoff fails
        """
        # Build request payload based on implementation plan
        payload = {
            "user_id": user_id,
            "summary_id": summary_id,
            "summary_pdf_url": summary_pdf_url,
            "lawyer_id": lawyer_id,
            "legal_area": legal_area,
            "case_strength": case_strength,
            "urgency": urgency,
        }

        if user_location:
            payload["user_location"] = user_location

        # Make request to sumii-anwalt backend
        url = f"{self.base_url}/api/cases/handoff"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to hand off case to sumii-anwalt: {e}")
            if hasattr(e, "response") and e.response is not None:
                error_detail = e.response.text
                logger.error(f"Error response: {error_detail}")
            raise Exception(f"Failed to hand off case to lawyer: {str(e)}") from e


# Dependency injection
def get_anwalt_service() -> AnwaltService:
    """FastAPI dependency for AnwaltService

    Returns:
        AnwaltService instance
    """
    return AnwaltService()
