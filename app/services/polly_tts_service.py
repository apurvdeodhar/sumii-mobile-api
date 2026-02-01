"""
Amazon Polly TTS Service - High-quality text-to-speech synthesis

Uses Amazon Polly Neural voices for natural-sounding speech.
Supports German and English with high-quality neural voices.
"""

import asyncio
import logging
from functools import lru_cache
from typing import Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Neural voice configurations for each language
VOICE_CONFIG = {
    "de-DE": {
        "voice_id": "Vicki",  # German female neural voice
        "engine": "neural",
        "language_code": "de-DE",
    },
    "en-US": {
        "voice_id": "Joanna",  # US English female neural voice
        "engine": "neural",
        "language_code": "en-US",
    },
    "en-GB": {
        "voice_id": "Amy",  # British English female neural voice
        "engine": "neural",
        "language_code": "en-GB",
    },
}

# Default language if not specified
DEFAULT_LANGUAGE = "de-DE"

# Audio format configuration
AUDIO_FORMAT: Literal["mp3", "ogg_vorbis", "pcm"] = "mp3"
SAMPLE_RATE = "22050"  # Hz - good balance of quality and size


class PollyTTSService:
    """Amazon Polly Text-to-Speech Service"""

    def __init__(self):
        """Initialize Polly client using AWS credentials from environment"""
        try:
            self.polly_client = boto3.client(
                "polly",
                region_name=settings.AWS_REGION,
            )
            logger.info(f"Polly TTS Service initialized (region: {settings.AWS_REGION})")
        except Exception as e:
            logger.error(f"Failed to initialize Polly client: {e}")
            self.polly_client = None

    def _strip_markdown(self, text: str) -> str:
        """
        Remove markdown formatting for cleaner TTS output.
        Polly doesn't understand markdown, so we clean it up.
        """
        import re

        result = text
        # Remove headers
        result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)
        # Remove bold/italic
        result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
        result = re.sub(r"\*(.+?)\*", r"\1", result)
        result = re.sub(r"__(.+?)__", r"\1", result)
        result = re.sub(r"_(.+?)_", r"\1", result)
        # Remove inline code
        result = re.sub(r"`(.+?)`", r"\1", result)
        # Remove code blocks
        result = re.sub(r"```[\s\S]*?```", "", result)
        # Remove links but keep text
        result = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", result)
        # Remove bullet points
        result = re.sub(r"^[-*+]\s+", "", result, flags=re.MULTILINE)
        # Remove numbered lists
        result = re.sub(r"^\d+\.\s+", "", result, flags=re.MULTILINE)
        # Clean up extra whitespace
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    async def synthesize_speech(
        self,
        text: str,
        language: str = DEFAULT_LANGUAGE,
        output_format: Literal["mp3", "ogg_vorbis", "pcm"] = AUDIO_FORMAT,
    ) -> bytes | None:
        """
        Synthesize speech from text using Amazon Polly Neural voices.

        Args:
            text: Text to convert to speech (markdown will be stripped)
            language: Language code (de-DE, en-US, en-GB)
            output_format: Audio format (mp3, ogg_vorbis, pcm)

        Returns:
            Audio data as bytes, or None on error
        """
        if not self.polly_client:
            logger.error("Polly client not initialized")
            return None

        # Clean the text
        clean_text = self._strip_markdown(text)
        if not clean_text:
            logger.warning("No text after stripping markdown")
            return None

        # Get voice configuration for language
        voice_config = VOICE_CONFIG.get(language, VOICE_CONFIG[DEFAULT_LANGUAGE])

        logger.info(
            f"Synthesizing speech: {len(clean_text)} chars, " f"voice={voice_config['voice_id']}, lang={language}"
        )

        try:
            # Run synchronous boto3 call in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.polly_client.synthesize_speech(
                    Text=clean_text,
                    OutputFormat=output_format,
                    VoiceId=voice_config["voice_id"],
                    Engine=voice_config["engine"],
                    LanguageCode=voice_config["language_code"],
                    SampleRate=SAMPLE_RATE,
                ),
            )

            # Read audio stream
            if "AudioStream" in response:
                audio_data = response["AudioStream"].read()
                logger.info(f"Speech synthesized: {len(audio_data)} bytes")
                return audio_data
            else:
                logger.error("No AudioStream in Polly response")
                return None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"Polly ClientError ({error_code}): {e}")
            return None
        except BotoCoreError as e:
            logger.error(f"Polly BotoCoreError: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in Polly synthesis: {e}")
            return None

    async def get_available_voices(self, language_code: str | None = None) -> list[dict]:
        """
        Get list of available Polly voices.

        Args:
            language_code: Optional filter by language (e.g., 'de-DE')

        Returns:
            List of voice info dictionaries
        """
        if not self.polly_client:
            return []

        try:
            loop = asyncio.get_event_loop()

            # Build kwargs for describe_voices
            kwargs = {}
            if language_code:
                kwargs["LanguageCode"] = language_code

            response = await loop.run_in_executor(None, lambda: self.polly_client.describe_voices(**kwargs))

            voices = response.get("Voices", [])
            return [
                {
                    "id": v["Id"],
                    "name": v["Name"],
                    "language": v["LanguageCode"],
                    "gender": v["Gender"],
                    "engine": v.get("SupportedEngines", ["standard"]),
                }
                for v in voices
            ]
        except Exception as e:
            logger.error(f"Failed to get Polly voices: {e}")
            return []


@lru_cache()
def get_polly_tts_service() -> PollyTTSService:
    """Get singleton Polly TTS service instance"""
    return PollyTTSService()
