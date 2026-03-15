"""PDF Service - Convert markdown and templates to PDF using WeasyPrint

This service handles conversion of legal summaries from markdown to PDF
with proper legal document styling.

It supports two methods:
1. markdown_to_pdf: Convert markdown text to PDF (legacy)
2. template_to_pdf: Render Jinja2 template with case data (professional output)
"""

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

logger = logging.getLogger(__name__)

# Path to templates directory (inside app folder to be included in Docker)
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_pdf_translations(language: str) -> dict[str, str]:
    """Get translation strings for PDF template headers.

    Returns a dict of label keys → translated strings for the given language.
    Default is German (de). English (en) is the only other supported language.
    """
    if language == "en":
        return {
            "confidential": "Confidential",
            "title": "Forensic Intake Report regarding",
            "regarding": "regarding",
            "reference": "Reference:",
            "created": "Created:",
            "claimant": "Claimant",
            "respondent": "Respondent",
            "name": "Name:",
            "role": "Role:",
            "address": "Address:",
            "contact": "Contact:",
            "legal_insurance": "Legal Insurance:",
            "insurance_company": "Insurance Company:",
            "insurance_number": "Policy Number:",
            "dob": "Date of Birth:",
            "occupation": "Occupation:",
            "claim_value": "Estimated Claim Value",
            "claim_amount": "Claim Value:",
            "claim_desc": "Description:",
            "facts": "Statement of Facts",
            "client_goal": "Client's Objective",
            "party_relationship": "Relationship Between Parties",
            "chronological_facts": "Chronological Facts",
            "date_unknown": "Date unknown",
            "prior_steps": "Prior Legal Steps",
            "witnesses": "Witnesses",
            "jurisdiction": "Relevant Court:",
            "evidence": "Evidence Index",
            "exhibit": "Exhibit",
            "document": "Document",
            "date_label": "Date:",
            "deadlines": "Known Deadlines",
            "financial": "Financial Information",
            "next_steps": "Next Steps",
            "next_step_1": "Contact the client through Sumii for further details",
            "next_step_2": "Review the provided documents",
            "next_step_3": "Schedule an initial consultation if needed",
            "legal_notice": "Legal Notice",
            "ai_notice": "AI-Generated Analysis:",
            "ai_notice_text": (
                "This forensic intake report was created with AI assistance and serves solely "
                "for the structured preparation of client information. It does not constitute legal advice."
            ),
            "review_notice": "Review Required:",
            "review_notice_text": (
                "All information is based on client statements and was automatically structured. "
                "Independent legal review is mandatory."
            ),
            "no_mandate": "No Attorney-Client Relationship:",
            "no_mandate_text": (
                "This analysis does not establish an attorney-client relationship. "
                "A mandate requires a separate agreement."
            ),
            "privacy": "Data Protection:",
            "privacy_text": "Processing complies with GDPR. All information is treated confidentially.",
            "attachments": "Attachments",
            "attachments_desc": "The following documents were uploaded by the client and are attached to this report:",
            "attachment": "Attachment",
            "not_specified": "Not specified",
            "declined_by_client": "Not specified (declined by client)",
            "draft": "SUMII-DRAFT",
            "client_label": "Sumii Client",
            "legal_claim": "Legal Claim",
        }
    # Default: German
    return {
        "confidential": "Vertraulich",
        "title": "Forensische Anamnese in Sachen",
        "regarding": "wegen",
        "reference": "Aktenzeichen:",
        "created": "Erstellt am:",
        "claimant": "Anspruchsteller",
        "respondent": "Anspruchsgegner",
        "name": "Name:",
        "role": "Rolle:",
        "address": "Anschrift:",
        "contact": "Kontakt:",
        "legal_insurance": "Rechtsschutzversicherung:",
        "insurance_company": "Versicherungsgesellschaft:",
        "insurance_number": "Versicherungsnummer:",
        "dob": "Geburtsdatum:",
        "occupation": "Beruf:",
        "claim_value": "Geschätzter Gegenstandswert",
        "claim_amount": "Streitwert:",
        "claim_desc": "Beschreibung:",
        "facts": "Sachverhaltsdarstellung",
        "client_goal": "Ziel des Mandanten",
        "party_relationship": "Verhältnis der Parteien",
        "chronological_facts": "Chronologischer Sachverhalt",
        "date_unknown": "Datum unbekannt",
        "prior_steps": "Bisherige rechtliche Schritte",
        "witnesses": "Zeugen",
        "jurisdiction": "Zuständiges Gericht:",
        "evidence": "Beweisverzeichnis",
        "exhibit": "Anlage",
        "document": "Dokument",
        "date_label": "Datum:",
        "deadlines": "Bekannte Fristen",
        "financial": "Finanzielle Angaben",
        "next_steps": "Nächste Schritte",
        "next_step_1": "Kontaktieren Sie den Mandanten über sumii für weitere Details",
        "next_step_2": "Prüfen Sie die bereitgestellten Unterlagen",
        "next_step_3": "Vereinbaren Sie ggf. ein Erstgespräch zur Mandatierung",
        "legal_notice": "Rechtliche Hinweise",
        "ai_notice": "KI-generierte Analyse:",
        "ai_notice_text": (
            "Diese forensische Anamnese wurde mit KI-Unterstützung erstellt und dient "
            "ausschließlich der strukturierten Aufbereitung von Mandanteninformationen. "
            "Sie stellt keine rechtliche Beratung dar."
        ),
        "review_notice": "Prüfungspflicht:",
        "review_notice_text": (
            "Alle Angaben basieren auf den Informationen des Mandanten und wurden automatisiert "
            "strukturiert. Eine eigenständige anwaltliche Prüfung ist zwingend erforderlich."
        ),
        "no_mandate": "Kein Mandatsverhältnis:",
        "no_mandate_text": (
            "Durch diese Analyse entsteht kein Mandatsverhältnis. "
            "Ein Mandat kommt erst durch gesonderte Vereinbarung zustande."
        ),
        "privacy": "Datenschutz:",
        "privacy_text": (
            "Die Verarbeitung erfolgt unter Beachtung der DSGVO. " "Alle Informationen werden vertraulich behandelt."
        ),
        "attachments": "Anlagen",
        "attachments_desc": (
            "Die folgenden Dokumente wurden vom Mandanten hochgeladen " "und sind diesem Bericht als Anlagen beigefügt:"
        ),
        "attachment": "Anlage",
        "not_specified": "Nicht angegeben",
        "declined_by_client": "Nicht angegeben (vom Mandanten abgelehnt)",
        "draft": "SUMII-ENTWURF",
        "client_label": "Sumii-Mandant",
        "legal_claim": "Rechtlicher Anspruch",
    }


class PDFService:
    """Service for converting markdown/templates to PDF"""

    def __init__(self):
        """Initialize PDF service with Jinja2 environment"""
        # Initialize Jinja2 environment for template rendering
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Register custom Jinja2 filters
        self.jinja_env.filters["default_if_empty"] = self._default_if_empty
        self.jinja_env.filters["format_german_date"] = self._format_german_date
        self.jinja_env.filters["truncate_words"] = self._truncate_words
        self.jinja_env.filters["nl2br"] = self._nl2br

        # Legal document CSS styling (for markdown method)
        self.css_style = """
        @page {
            size: A4;
            margin: 2.5cm 2cm;
            @top-center {
                content: "Sumii - Forensische Anamnese";
                font-size: 10pt;
                color: #666;
            }
            @bottom-center {
                content: "Seite " counter(page) " von " counter(pages);
                font-size: 10pt;
                color: #666;
            }
        }

        body {
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }

        h1 {
            font-size: 20pt;
            font-weight: bold;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            color: #1a1a1a;
            border-bottom: 2px solid #333;
            padding-bottom: 0.3em;
        }

        h2 {
            font-size: 16pt;
            font-weight: bold;
            margin-top: 1.2em;
            margin-bottom: 0.4em;
            color: #2a2a2a;
        }

        h3 {
            font-size: 13pt;
            font-weight: bold;
            margin-top: 1em;
            margin-bottom: 0.3em;
            color: #3a3a3a;
        }

        p {
            margin: 0.8em 0;
            text-align: justify;
        }

        ul, ol {
            margin: 0.8em 0;
            padding-left: 2em;
        }

        li {
            margin: 0.4em 0;
        }

        strong {
            font-weight: bold;
            color: #1a1a1a;
        }

        em {
            font-style: italic;
        }

        code {
            font-family: 'Courier New', monospace;
            font-size: 10pt;
            background-color: #f5f5f5;
            padding: 0.2em 0.4em;
            border-radius: 3px;
        }

        blockquote {
            border-left: 4px solid #ccc;
            padding-left: 1em;
            margin: 1em 0;
            color: #666;
        }

        hr {
            border: none;
            border-top: 1px solid #ccc;
            margin: 2em 0;
        }

        /* Legal document specific */
        .reference-number {
            font-size: 12pt;
            font-weight: bold;
            color: #1a1a1a;
            margin-bottom: 1em;
        }

        .disclaimer {
            font-size: 9pt;
            color: #666;
            font-style: italic;
            margin-top: 2em;
            padding-top: 1em;
            border-top: 1px solid #ddd;
        }
        """

    # Custom Jinja2 filters
    @staticmethod
    def _default_if_empty(value, default="k. A."):
        """Return default if value is empty or None"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return value

    @staticmethod
    def _format_german_date(value):
        """Format date in German format (DD.MM.YYYY)"""
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y")
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value)
                return dt.strftime("%d.%m.%Y")
            except (ValueError, TypeError):
                return value
        return value or datetime.now().strftime("%d.%m.%Y")

    @staticmethod
    def _truncate_words(value, num_words=3):
        """Truncate text to specified number of words"""
        if not value:
            return ""
        words = str(value).split()
        if len(words) <= num_words:
            return value
        return " ".join(words[:num_words]) + "..."

    @staticmethod
    def _nl2br(value):
        """Convert newlines to <br> tags"""
        if not value:
            return ""
        return str(value).replace("\n", "<br>\n")

    def template_to_pdf(
        self,
        case_data: dict,
        summary_id: str | None = None,
        template_name: str = "legal_case_report.html",
        is_lawyer_view: bool = False,
        attached_documents: list[dict] | None = None,
        language: str = "de",
    ) -> bytes:
        """Render Jinja2 template with case data and convert to PDF

        This is the preferred method for generating professional legal summaries.

        Args:
            case_data: Dictionary with case information matching template structure:
                - claimant: dict with name, legal_insurance, etc.
                - respondent: dict with name, address, contact
                - factual_narrative: dict with legal_desire, party_relationship, timeline
                - evidence: dict with evidence_items list
                - financial_info: dict with claim_value_eur
            summary_id: Summary UUID for reference number
            template_name: Name of template file (default: legal_case_report.html)
            is_lawyer_view: If True, anonymizes user personal data (name, contact)
            attached_documents: Optional list of dicts with 'filename' key for Anlage cover page

        Returns:
            bytes: PDF file content

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Load template
            template = self.jinja_env.get_template(template_name)

            # Get logo path (WeasyPrint needs file:// URL or base64)
            assets_dir = Path(__file__).parent.parent / "assets"
            logo_path = assets_dir / "sumii_logo.png"
            logo_url = f"file://{logo_path}" if logo_path.exists() else None

            # Build translation dict for bilingual PDF support
            t = _get_pdf_translations(language)

            # Prepare template context
            context = {
                "case_data": case_data,
                "summary_id": summary_id or "SUMII-DRAFT",
                "session_id": summary_id,
                "generation_date": datetime.now(),
                "template_version": "2.0",
                "language": language,
                "t": t,
                "logo_path": logo_url,
                "is_lawyer_view": is_lawyer_view,
                "attached_documents": attached_documents or [],
            }

            # Render template to HTML
            html_content = template.render(**context)

            # Convert HTML to PDF
            font_config = FontConfiguration()
            html_doc = HTML(string=html_content)
            pdf_bytes = html_doc.write_pdf(font_config=font_config)

            logger.info(f"Generated PDF from template: {len(pdf_bytes)} bytes (lawyer_view={is_lawyer_view})")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF from template: {e}", exc_info=True)
            raise Exception(f"PDF generation from template failed: {str(e)}") from e

    def merge_with_documents(
        self,
        summary_pdf: bytes,
        documents: list[tuple[str, str, bytes]],
    ) -> bytes:
        """Merge summary PDF with document attachments as appendix pages.

        Args:
            summary_pdf: The WeasyPrint-generated summary PDF bytes
            documents: List of (filename, file_type, content_bytes) tuples

        Returns:
            Merged PDF bytes with documents appended after the summary
        """
        writer = PdfWriter()

        # Add all summary pages
        summary_reader = PdfReader(BytesIO(summary_pdf))
        for page in summary_reader.pages:
            writer.add_page(page)

        # For each document, convert if needed and append
        for filename, file_type, content in documents:
            try:
                if file_type == "application/pdf":
                    doc_reader = PdfReader(BytesIO(content))
                    for page in doc_reader.pages:
                        writer.add_page(page)
                elif file_type.startswith("image/"):
                    img_pdf = self._image_to_pdf_page(content, file_type)
                    img_reader = PdfReader(BytesIO(img_pdf))
                    for page in img_reader.pages:
                        writer.add_page(page)
                else:
                    logger.warning(f"Skipping unsupported file type for merge: {file_type} ({filename})")
            except Exception as e:
                logger.warning(f"Failed to merge document '{filename}': {e}")

        # Write merged PDF
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    @staticmethod
    def _image_to_pdf_page(image_bytes: bytes, file_type: str) -> bytes:
        """Convert an image to a single-page PDF.

        Handles JPEG, PNG, HEIC/HEIF formats. HEIC requires pillow-heif.

        Args:
            image_bytes: Raw image bytes
            file_type: MIME type (image/jpeg, image/png, image/heic, image/heif)

        Returns:
            PDF bytes containing the image as a single page
        """
        from PIL import Image

        # HEIC/HEIF support requires pillow-heif plugin (auto-registered if installed)
        if file_type in ("image/heic", "image/heif"):
            try:
                import pillow_heif

                pillow_heif.register_heif_opener()
            except ImportError:
                logger.warning("pillow-heif not installed — HEIC images will fail to convert")

        img = Image.open(BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output = BytesIO()
        img.save(output, format="PDF")
        return output.getvalue()

    def markdown_to_pdf(self, markdown_content: str, reference_number: str | None = None) -> bytes:
        """Convert markdown to PDF bytes (legacy method)

        Args:
            markdown_content: Markdown text content
            reference_number: Optional reference number to include in PDF

        Returns:
            bytes: PDF file content

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Convert markdown to HTML
            html_content = md.markdown(
                markdown_content,
                extensions=["extra", "codehilite", "tables"],
            )

            # Add reference number if provided
            if reference_number:
                reference_html = f'<div class="reference-number">Aktenzeichen: {reference_number}</div>'
                html_content = reference_html + "\n\n" + html_content

            # Wrap in full HTML document
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Forensische Anamnese</title>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

            # Convert HTML to PDF
            font_config = FontConfiguration()
            html_doc = HTML(string=full_html)
            pdf_bytes = html_doc.write_pdf(
                stylesheets=[CSS(string=self.css_style)],
                font_config=font_config,
            )

            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}", exc_info=True)
            raise Exception(f"PDF generation failed: {str(e)}") from e
