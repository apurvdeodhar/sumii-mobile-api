"""OCR Service - Extract text from documents using Mistral AI

This service uses Mistral's OCR API (via Pixtral vision model) to extract
text from uploaded documents (PDFs, images). The extracted text is used for:
1. Enriching conversation context
2. Building evidence list (Beweisverzeichnis/Anhang) for summaries
3. Extracting dates and facts for chronological storytelling
"""

import base64
import logging

from mistralai import Mistral

from app.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """Service for extracting text from documents using Mistral OCR API

    Uses Mistral's OCR endpoint which leverages Pixtral vision model
    for high-quality text extraction with document structure preservation.
    """

    def __init__(self):
        """Initialize OCR service with Mistral client"""
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        # Model for image OCR processing (vision model)
        # For PDF OCR, we use mistral-ocr-latest via the dedicated OCR endpoint
        self.model = "pixtral-large-latest"

    async def extract_text_from_bytes(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
    ) -> str:
        """Extract text from document bytes using Mistral OCR

        Args:
            file_content: Raw bytes of the document
            file_type: MIME type (e.g., "application/pdf", "image/jpeg")
            filename: Original filename for logging

        Returns:
            str: Extracted text from document, or empty string on failure
        """
        try:
            logger.info(f"[OCR] Processing {filename} ({file_type})")

            # For images, use Pixtral vision chat
            if file_type.startswith("image/"):
                return await self._process_image(file_content, file_type, filename)

            # For PDFs, use OCR endpoint
            elif file_type == "application/pdf":
                return await self._process_pdf(file_content, filename)

            else:
                logger.warning(f"[OCR] Unsupported file type: {file_type}")
                return ""

        except Exception as e:
            logger.error(f"[OCR] Failed to process {filename}: {e}")
            return ""

    async def _process_image(
        self,
        file_content: bytes,
        file_type: str,
        filename: str,
    ) -> str:
        """Process image using Pixtral vision model

        Args:
            file_content: Image bytes
            file_type: MIME type (image/jpeg, image/png, etc.)
            filename: Original filename

        Returns:
            str: Extracted text from image
        """
        # Convert bytes to base64 data URI
        base64_data = base64.b64encode(file_content).decode("utf-8")
        data_uri = f"data:{file_type};base64,{base64_data}"

        # Use Pixtral chat to extract text
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extrahiere den gesamten Text aus diesem Dokument/Bild.
Behalte die Struktur bei (Überschriften, Listen, Tabellen).
Extrahiere auch alle wichtigen Daten wie:
- Datumsangaben (z.B. "gültig bis 05.02.2020")
- Namen und Adressen
- Beträge und Zahlen
- Unterschriften oder Stempel (notiere als [Unterschrift] oder [Stempel])

Antworte NUR mit dem extrahierten Text, keine Erklärungen.""",
                        },
                        {
                            "type": "image_url",
                            "image_url": data_uri,
                        },
                    ],
                }
            ],
        )

        extracted_text = response.choices[0].message.content or ""
        logger.info(f"[OCR] Extracted {len(extracted_text)} chars from image {filename}")
        return extracted_text

    async def _process_pdf(
        self,
        file_content: bytes,
        filename: str,
    ) -> str:
        """Process PDF using Mistral OCR endpoint

        Args:
            file_content: PDF bytes
            filename: Original filename

        Returns:
            str: Extracted text from PDF
        """
        # Convert bytes to base64 data URI for PDF
        base64_data = base64.b64encode(file_content).decode("utf-8")
        data_uri = f"data:application/pdf;base64,{base64_data}"

        # Use OCR endpoint for PDFs
        try:
            response = self.client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": data_uri,
                },
            )

            # Combine all pages/sections into single text
            all_text = []
            if hasattr(response, "pages"):
                for page in response.pages:
                    if hasattr(page, "markdown"):
                        all_text.append(page.markdown)
                    elif hasattr(page, "text"):
                        all_text.append(page.text)

            extracted_text = "\n\n".join(all_text)
            logger.info(f"[OCR] Extracted {len(extracted_text)} chars from PDF {filename}")
            return extracted_text

        except Exception as e:
            # Fallback: Use Pixtral for PDF (convert first page to image concept)
            logger.warning(f"[OCR] OCR endpoint failed for {filename}: {e}, falling back to vision model")
            return await self._process_pdf_with_vision(file_content, filename)

    async def _process_pdf_with_vision(
        self,
        file_content: bytes,
        filename: str,
    ) -> str:
        """Fallback: Process PDF using vision model if OCR endpoint fails

        Note: This is less accurate but provides a fallback option.
        """
        base64_data = base64.b64encode(file_content).decode("utf-8")
        data_uri = f"data:application/pdf;base64,{base64_data}"

        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Extrahiere den gesamten Text aus diesem PDF-Dokument.
Behalte die Struktur bei (Überschriften, Listen, Tabellen).
Extrahiere wichtige Daten wie Datumsangaben, Namen, Beträge.
Antworte NUR mit dem extrahierten Text.""",
                        },
                        {
                            "type": "image_url",
                            "image_url": data_uri,
                        },
                    ],
                }
            ],
        )

        extracted_text = response.choices[0].message.content or ""
        logger.info(f"[OCR] Extracted {len(extracted_text)} chars from PDF (vision fallback) {filename}")
        return extracted_text


# Singleton instance
_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    """Get or create OCR service singleton"""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
