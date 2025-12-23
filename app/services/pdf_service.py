"""PDF Service - Convert markdown and templates to PDF using WeasyPrint

This service handles conversion of legal summaries from markdown to PDF
with proper legal document styling.

It supports two methods:
1. markdown_to_pdf: Convert markdown text to PDF (legacy)
2. template_to_pdf: Render Jinja2 template with case data (professional output)
"""

import logging
from datetime import datetime
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

logger = logging.getLogger(__name__)

# Path to templates directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "docs" / "library" / "templates"


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

        Returns:
            bytes: PDF file content

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Load template
            template = self.jinja_env.get_template(template_name)

            # Prepare template context
            context = {
                "case_data": case_data,
                "summary_id": summary_id or "SUMII-DRAFT",
                "session_id": summary_id,
                "generation_date": datetime.now(),
                "template_version": "2.0",
                "language": "de",
            }

            # Render template to HTML
            html_content = template.render(**context)

            # Convert HTML to PDF
            font_config = FontConfiguration()
            html_doc = HTML(string=html_content)
            pdf_bytes = html_doc.write_pdf(font_config=font_config)

            logger.info(f"Generated PDF from template: {len(pdf_bytes)} bytes")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Failed to generate PDF from template: {e}", exc_info=True)
            raise Exception(f"PDF generation from template failed: {str(e)}") from e

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
