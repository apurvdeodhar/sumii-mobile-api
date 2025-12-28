"""Email Service - AWS SES integration for user verification and password reset

This service handles sending emails via AWS SES for:
- Email verification (on_after_request_verify)
- Password reset (on_after_forgot_password)
- Welcome email (on_after_register)
"""

# ruff: noqa: E501 - HTML email templates contain long lines due to inline CSS

import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via AWS SES"""

    def __init__(self):
        """Initialize AWS SES client

        Uses explicit credentials if provided, otherwise falls back to
        boto3 default credential chain (~/.aws/credentials or IAM role).
        """
        try:
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                # Explicit credentials provided
                self.ses_client = boto3.client(
                    "ses",
                    region_name=settings.AWS_REGION,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
            else:
                # Use default boto3 credential chain (~/.aws/credentials, IAM role, etc.)
                self.ses_client = boto3.client(
                    "ses",
                    region_name=settings.AWS_REGION,
                )
            self.from_email = settings.SES_FROM_EMAIL
            logger.info("Email service initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize email service: {e}")
            self.ses_client = None
            self.from_email = None

    def _build_branded_email(
        self,
        title: str,
        message: str,
        cta_text: str,
        cta_url: str,
        fallback_text: str,
        fallback_url: str,
        expiry_text: str,
        language: str = "de",
    ) -> str:
        """Build a branded email template with consistent Sumii styling.

        Args:
            title: Email heading
            message: Main message text
            cta_text: Call-to-action button text
            cta_url: Call-to-action button URL
            fallback_text: Text for fallback link
            fallback_url: Fallback URL
            expiry_text: Expiry/additional info text
            language: Language code for footer

        Returns:
            HTML email content
        """
        tagline = "IHR INTELLIGENTER RECHTSASSISTENT" if language == "de" else "YOUR INTELLIGENT LEGAL ASSISTANT"
        footer_greeting = "Mit freundlichen Grüßen," if language == "de" else "Best regards,"
        footer_team = "Ihr sumii Team" if language == "de" else "Your sumii Team"

        return f"""
        <!DOCTYPE html>
        <html lang="{language}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Figtree', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background-color: #f8fafc;">
            <table role="presentation" style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td align="center" style="padding: 40px 20px;">
                        <table role="presentation" style="width: 100%; max-width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 14px rgba(52, 73, 94, 0.15);">

                            <!-- Header with gradient and logo -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #34495e 0%, #7b8d9f 100%); padding: 40px 30px; text-align: center;">
                                    <img src="https://sumii-assets.s3.eu-central-1.amazonaws.com/logos/logo-dark.png" alt="sumii" style="width: 120px; height: auto; margin-bottom: 12px;" />
                                    <p style="margin: 0; font-size: 14px; color: rgba(255,255,255,0.8); letter-spacing: 1px;">{tagline}</p>
                                </td>
                            </tr>

                            <!-- Main content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 16px 0; font-size: 24px; font-weight: 600; color: #34495e;">
                                        {title}
                                    </h2>
                                    <p style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #4a5568;">
                                        {message}
                                    </p>

                                    <!-- CTA Button -->
                                    <table role="presentation" style="width: 100%; margin: 24px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="{cta_url}" style="display: inline-block; padding: 16px 40px; background: linear-gradient(135deg, #34495e 0%, #7b8d9f 100%); color: #ffffff; font-size: 16px; font-weight: 600; text-decoration: none; border-radius: 10px; box-shadow: 0 4px 14px rgba(52, 73, 94, 0.25);">
                                                    {cta_text}
                                                </a>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- Fallback link -->
                                    <p style="margin: 24px 0 8px 0; font-size: 13px; color: #7b8d9f;">
                                        {fallback_text}
                                    </p>
                                    <p style="margin: 0; font-size: 12px; color: #a0aec0; word-break: break-all;">
                                        {fallback_url}
                                    </p>

                                    <!-- Expiry info -->
                                    <p style="margin: 24px 0 0 0; font-size: 13px; color: #7b8d9f;">
                                        {expiry_text}
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f8fafc; padding: 24px 30px; border-top: 1px solid #e2e8f0;">
                                    <p style="margin: 0 0 8px 0; font-size: 12px; color: #7b8d9f; text-align: center;">
                                        {footer_greeting}<br>
                                        <strong style="color: #34495e;">{footer_team}</strong>
                                    </p>
                                    <p style="margin: 0; font-size: 11px; color: #a0aec0; text-align: center;">
                                        sumii • Hamburg, Germany<br>
                                        <a href="https://sumii.de" style="color: #7b8d9f; text-decoration: none;">sumii.de</a> •
                                        <a href="mailto:info@sumii.de" style="color: #7b8d9f; text-decoration: none;">info@sumii.de</a>
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    async def send_verification_email(self, user_email: str, token: str, language: str = "de") -> None:
        """Send email verification link to user

        Args:
            user_email: User's email address
            token: Verification token
            language: User's preferred language ("de" or "en")
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - verification email not sent to {user_email}")
            return

        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        is_german = language == "de"

        if is_german:
            subject = "Bestätigen Sie Ihre sumii E-Mail-Adresse"
            title = "E-Mail bestätigen"
            message = "Bitte bestätigen Sie Ihre E-Mail-Adresse, um Ihr sumii-Konto zu aktivieren."
            cta_text = "E-Mail bestätigen →"
            fallback = "Falls der Button nicht funktioniert, kopieren Sie diesen Link:"
            expiry = "Dieser Link ist 24 Stunden gültig."
        else:
            subject = "Verify your sumii email address"
            title = "Verify Email"
            message = "Please verify your email address to activate your sumii account."
            cta_text = "Verify Email →"
            fallback = "If the button doesn't work, copy this link:"
            expiry = "This link expires in 24 hours."

        body_html = self._build_branded_email(
            title=title,
            message=message,
            cta_text=cta_text,
            cta_url=verification_url,
            fallback_text=fallback,
            fallback_url=verification_url,
            expiry_text=expiry,
            language=language,
        )

        body_text = f"""
{title}

{message}

{cta_text}: {verification_url}

{expiry}

---
sumii • Hamburg, Germany
https://sumii.de • info@sumii.de
        """

        await self._send_email(user_email, subject, body_text, body_html)

    async def send_password_reset_email(self, user_email: str, token: str, language: str = "de") -> None:
        """Send password reset link to user

        Args:
            user_email: User's email address
            token: Password reset token
            language: User's preferred language ("de" or "en")
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - password reset email not sent to {user_email}")
            return

        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        is_german = language == "de"

        if is_german:
            subject = "Passwort zurücksetzen - sumii"
            title = "Passwort zurücksetzen"
            message = "Sie haben angefordert, Ihr Passwort zurückzusetzen. Klicken Sie auf den Button unten, um ein neues Passwort zu wählen."
            cta_text = "Passwort zurücksetzen →"
            fallback = "Falls der Button nicht funktioniert, kopieren Sie diesen Link:"
            expiry = "Dieser Link ist 1 Stunde gültig."
            ignore = "Falls Sie dies nicht angefordert haben, können Sie diese E-Mail ignorieren."
        else:
            subject = "Reset Password - sumii"
            title = "Reset Password"
            message = "You requested to reset your password. Click the button below to choose a new password."
            cta_text = "Reset Password →"
            fallback = "If the button doesn't work, copy this link:"
            expiry = "This link expires in 1 hour."
            ignore = "If you didn't request this, you can ignore this email."

        body_html = self._build_branded_email(
            title=title,
            message=message,
            cta_text=cta_text,
            cta_url=reset_url,
            fallback_text=fallback,
            fallback_url=reset_url,
            expiry_text=f"{expiry} {ignore}",
            language=language,
        )

        body_text = f"""
{title}

{message}

{cta_text}: {reset_url}

{expiry}
{ignore}

---
sumii • Hamburg, Germany
https://sumii.de • info@sumii.de
        """

        await self._send_email(user_email, subject, body_text, body_html)

    async def send_lawyer_response_email(self, user_email: str, lawyer_name: str, case_summary_url: str) -> None:
        """Send email to user when lawyer responds to their case

        Args:
            user_email: User's email address
            lawyer_name: Name of the lawyer who responded
            case_summary_url: URL to view the case summary (frontend URL)
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - lawyer response email not sent to {user_email}")
            return

        subject = "Ihr Anwalt hat geantwortet"
        body_html = f"""
        <html>
        <body>
            <h2>Ihr Anwalt hat geantwortet</h2>
            <p>Hallo,</p>
            <p>{lawyer_name} hat auf Ihren Fall geantwortet.</p>
            <p><a href="{case_summary_url}">Antwort ansehen</a></p>
            <p>Wenn der Link nicht funktioniert, kopieren Sie diese URL in Ihren Browser:</p>
            <p>{case_summary_url}</p>
            <p>Mit freundlichen Grüßen,<br>Ihr Sumii Team</p>
        </body>
        </html>
        """
        body_text = f"""
        Ihr Anwalt hat geantwortet

        Hallo,

        {lawyer_name} hat auf Ihren Fall geantwortet.

        Antwort ansehen: {case_summary_url}

        Mit freundlichen Grüßen,
        Ihr Sumii Team
        """

        await self._send_email(user_email, subject, body_text, body_html)

    async def send_welcome_email(self, user_email: str, language: str = "de") -> None:
        """Send welcome email to newly registered user

        Args:
            user_email: User's email address
            language: User's preferred language ("de" or "en"), defaults to German
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - welcome email not sent to {user_email}")
            return

        app_url = settings.FRONTEND_URL
        is_german = language == "de"

        # Language-specific content
        if is_german:
            subject = "Willkommen bei sumii! 🎉"
            tagline = "IHR INTELLIGENTER RECHTSASSISTENT"
            welcome_title = "Willkommen bei sumii! 🎉"
            welcome_text = "Vielen Dank für Ihre Registrierung! sumii ist Ihr intelligenter, einfühlsamer Rechtsassistent. Wir helfen Ihnen, Ihre rechtliche Situation zu verstehen und bereiten alle Informationen für einen Anwalt vor."
            features = [
                "Intelligente Fragen zu Ihrem Fall beantworten",
                "Übersichtliche Zusammenfassung erstellen",
                "Passenden Anwalt in Ihrer Nähe finden",
            ]
            cta_text = "Jetzt starten →"
            footer_greeting = "Mit freundlichen Grüßen,"
            footer_team = "Ihr sumii Team"
        else:
            subject = "Welcome to sumii! 🎉"
            tagline = "YOUR INTELLIGENT LEGAL ASSISTANT"
            welcome_title = "Welcome to sumii! 🎉"
            welcome_text = (
                "Thank you for registering! sumii is your intelligent, empathetic legal assistant. "
                "We help you understand your legal situation and prepare all information for a lawyer."
            )
            features = [
                "Answer intelligent questions about your case",
                "Create a clear summary of your situation",
                "Find a suitable lawyer near you",
            ]
            cta_text = "Get Started →"
            footer_greeting = "Best regards,"
            footer_team = "Your sumii Team"

        # Professional Sumii-branded HTML email template
        # Colors: urban-a0=#34495e, urban-a10=#7b8d9f
        body_html = f"""
        <!DOCTYPE html>
        <html lang="{language}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Figtree', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background-color: #f8fafc;">
            <table role="presentation" style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td align="center" style="padding: 40px 20px;">
                        <table role="presentation" style="width: 100%; max-width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 14px rgba(52, 73, 94, 0.15);">

                            <!-- Header with gradient and logo -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #34495e 0%, #7b8d9f 100%); padding: 40px 30px; text-align: center;">
                                    <img src="https://sumii-assets.s3.eu-central-1.amazonaws.com/logos/logo-dark.png" alt="sumii" style="width: 120px; height: auto; margin-bottom: 12px;" />
                                    <p style="margin: 0; font-size: 14px; color: rgba(255,255,255,0.8); letter-spacing: 1px;">{tagline}</p>
                                </td>
                            </tr>

                            <!-- Main content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 16px 0; font-size: 24px; font-weight: 600; color: #34495e;">
                                        {welcome_title}
                                    </h2>
                                    <p style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #4a5568;">
                                        {welcome_text}
                                    </p>

                                    <!-- Features list -->
                                    <table role="presentation" style="width: 100%; margin-bottom: 24px;">
                                        <tr>
                                            <td style="padding: 12px 0; border-bottom: 1px solid #e2e8f0;">
                                                <span style="display: inline-block; width: 24px; height: 24px; background-color: #34495e; border-radius: 50%; color: white; text-align: center; line-height: 24px; font-size: 12px; margin-right: 12px;">✓</span>
                                                <span style="color: #4a5568; font-size: 15px;">{features[0]}</span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px 0; border-bottom: 1px solid #e2e8f0;">
                                                <span style="display: inline-block; width: 24px; height: 24px; background-color: #34495e; border-radius: 50%; color: white; text-align: center; line-height: 24px; font-size: 12px; margin-right: 12px;">✓</span>
                                                <span style="color: #4a5568; font-size: 15px;">{features[1]}</span>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 12px 0;">
                                                <span style="display: inline-block; width: 24px; height: 24px; background-color: #34495e; border-radius: 50%; color: white; text-align: center; line-height: 24px; font-size: 12px; margin-right: 12px;">✓</span>
                                                <span style="color: #4a5568; font-size: 15px;">{features[2]}</span>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- CTA Button -->
                                    <table role="presentation" style="width: 100%; margin: 32px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="{app_url}" style="display: inline-block; padding: 16px 40px; background: linear-gradient(135deg, #34495e 0%, #7b8d9f 100%); color: #ffffff; font-size: 16px; font-weight: 600; text-decoration: none; border-radius: 10px; box-shadow: 0 4px 14px rgba(52, 73, 94, 0.25);">
                                                    {cta_text}
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f8fafc; padding: 24px 30px; border-top: 1px solid #e2e8f0;">
                                    <p style="margin: 0 0 8px 0; font-size: 12px; color: #7b8d9f; text-align: center;">
                                        {footer_greeting}<br>
                                        <strong style="color: #34495e;">{footer_team}</strong>
                                    </p>
                                    <p style="margin: 0; font-size: 11px; color: #a0aec0; text-align: center;">
                                        sumii • Hamburg, Germany<br>
                                        <a href="https://sumii.de" style="color: #7b8d9f; text-decoration: none;">sumii.de</a> •
                                        <a href="mailto:info@sumii.de" style="color: #7b8d9f; text-decoration: none;">info@sumii.de</a>
                                    </p>
                                </td>
                            </tr>

                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        # Plain text version
        features_text = "\n".join([f"✓ {f}" for f in features])
        body_text = f"""
{welcome_title}

{welcome_text}

{features_text}

{cta_text}: {app_url}

---

{footer_greeting}
{footer_team}

sumii • Hamburg, Germany
https://sumii.de • info@sumii.de
        """

        await self._send_email(user_email, subject, body_text, body_html)

    async def _send_email(self, to_email: str, subject: str, body_text: str, body_html: str) -> None:
        """Send email via AWS SES

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_text: Plain text email body
            body_html: HTML email body
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - email not sent to {to_email}")
            return

        try:
            # boto3 SES client is synchronous, so we run it in executor for async compatibility
            import asyncio

            def send_email():
                return self.ses_client.send_email(
                    Source=self.from_email,
                    Destination={"ToAddresses": [to_email]},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": {
                            "Text": {"Data": body_text, "Charset": "UTF-8"},
                            "Html": {"Data": body_html, "Charset": "UTF-8"},
                        },
                    },
                )

            response = await asyncio.to_thread(send_email)
            logger.info(f"Email sent successfully to {to_email}. MessageId: {response['MessageId']}")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.error(f"Failed to send email to {to_email}: {error_code} - {e}")
            # Don't raise exception - email sending failure shouldn't break user registration
            # Log error but continue execution


# Dependency injection
def get_email_service() -> EmailService:
    """FastAPI dependency for Email service"""
    return EmailService()
