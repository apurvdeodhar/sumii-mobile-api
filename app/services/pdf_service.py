"""PDF Service - Convert markdown to PDF using WeasyPrint

This service handles conversion of legal summaries from markdown to PDF
with proper legal document styling.
"""

import logging

import markdown
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

logger = logging.getLogger(__name__)


class PDFService:
    """Service for converting markdown to PDF"""

    def __init__(self):
        """Initialize PDF service"""
        # Legal document CSS styling
        self.css_style = """
        @page {
            size: A4;
            margin: 2.5cm 2cm;
            @top-center {
                content: "Sumii - Rechtliche Zusammenfassung";
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

    def markdown_to_pdf(self, markdown_content: str, reference_number: str | None = None) -> bytes:
        """Convert markdown to PDF bytes

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
            html_content = markdown.markdown(
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
                <title>Rechtliche Zusammenfassung</title>
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
