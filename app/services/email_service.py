"""Email Service - AWS SES integration for user verification and password reset

This service handles sending emails via AWS SES for:
- Email verification (on_after_request_verify)
- Password reset (on_after_forgot_password)
"""

import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via AWS SES"""

    def __init__(self):
        """Initialize AWS SES client"""
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.ses_client = boto3.client(
                "ses",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            self.from_email = settings.SES_FROM_EMAIL
        else:
            logger.warning("AWS credentials not configured - email service disabled")
            self.ses_client = None
            self.from_email = None

    async def send_verification_email(self, user_email: str, token: str) -> None:
        """Send email verification link to user

        Args:
            user_email: User's email address
            token: Verification token
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - verification email not sent to {user_email}")
            return

        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        subject = "Verify your Sumii email address"
        body_html = f"""
        <html>
        <body>
            <h2>Welcome to Sumii!</h2>
            <p>Please verify your email address by clicking the link below:</p>
            <p><a href="{verification_url}">Verify Email</a></p>
            <p>If the link doesn't work, copy and paste this URL into your browser:</p>
            <p>{verification_url}</p>
            <p>This link will expire in 24 hours.</p>
        </body>
        </html>
        """
        body_text = f"""
        Welcome to Sumii!

        Please verify your email address by visiting this link:
        {verification_url}

        This link will expire in 24 hours.
        """

        await self._send_email(user_email, subject, body_text, body_html)

    async def send_password_reset_email(self, user_email: str, token: str) -> None:
        """Send password reset link to user

        Args:
            user_email: User's email address
            token: Password reset token
        """
        if not self.ses_client or not self.from_email:
            logger.warning(f"Email service disabled - password reset email not sent to {user_email}")
            return

        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        subject = "Reset your Sumii password"
        body_html = f"""
        <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>You requested to reset your password. Click the link below to reset it:</p>
            <p><a href="{reset_url}">Reset Password</a></p>
            <p>If the link doesn't work, copy and paste this URL into your browser:</p>
            <p>{reset_url}</p>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </body>
        </html>
        """
        body_text = f"""
        Password Reset Request

        You requested to reset your password. Visit this link to reset it:
        {reset_url}

        This link will expire in 1 hour.

        If you didn't request this, please ignore this email.
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
