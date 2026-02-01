"""
TTS API Endpoints - Text-to-Speech using Amazon Polly

Provides endpoints for synthesizing speech from text.
Uses neural voices for high-quality, natural-sounding audio.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.auth.jwt import get_current_user
from app.models import User
from app.services.polly_tts_service import get_polly_tts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class TTSRequest(BaseModel):
    """Request body for TTS synthesis"""

    text: str = Field(..., min_length=1, max_length=3000, description="Text to synthesize")
    language: Literal["de-DE", "en-US", "en-GB"] = Field(default="de-DE", description="Language for voice synthesis")


class TTSVoice(BaseModel):
    """Voice information"""

    id: str
    name: str
    language: str
    gender: str
    engine: list[str]


class VoicesResponse(BaseModel):
    """Response for available voices"""

    voices: list[TTSVoice]


@router.post(
    "/synthesize",
    summary="Synthesize speech from text",
    description=(
        "Convert text to speech using Amazon Polly neural voices. "
        "Returns MP3 audio data. Maximum 3000 characters per request."
    ),
    responses={
        200: {
            "content": {"audio/mpeg": {}},
            "description": "MP3 audio data",
        },
        400: {"description": "Invalid request"},
        500: {"description": "TTS synthesis failed"},
    },
)
async def synthesize_speech(
    request: TTSRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Synthesize speech from text.

    - **text**: The text to convert to speech (max 3000 chars)
    - **language**: Voice language (de-DE, en-US, en-GB)

    Returns MP3 audio data.
    """
    logger.info(f"TTS request: user={current_user.id}, lang={request.language}, " f"chars={len(request.text)}")

    tts_service = get_polly_tts_service()
    audio_data = await tts_service.synthesize_speech(
        text=request.text,
        language=request.language,
        output_format="mp3",
    )

    if audio_data is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to synthesize speech. Please try again.",
        )

    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/voices",
    response_model=VoicesResponse,
    summary="Get available TTS voices",
    description="List available voices for text-to-speech synthesis.",
)
async def get_voices(
    language: str | None = Query(None, description="Filter by language code (e.g., de-DE)"),
    current_user: User = Depends(get_current_user),
) -> VoicesResponse:
    """
    Get available TTS voices.

    - **language**: Optional filter by language code
    """
    tts_service = get_polly_tts_service()
    voices = await tts_service.get_available_voices(language_code=language)

    return VoicesResponse(voices=[TTSVoice(**v) for v in voices])
