"""Unit Tests for Email Service

Tests the EmailService class methods including lawyer response email.
"""

import pytest

pytestmark = pytest.mark.unit


class TestEmailService:
    """Test EmailService methods"""

    def test_send_lawyer_response_email_method_exists(self):
        """Test that EmailService has send_lawyer_response_email method"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        assert hasattr(email_service, "send_lawyer_response_email")
        assert callable(email_service.send_lawyer_response_email)

    @pytest.mark.asyncio
    async def test_send_lawyer_response_email_without_aws_credentials(self):
        """Test send_lawyer_response_email gracefully handles missing AWS credentials"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        # Should not raise exception even if AWS credentials not configured
        await email_service.send_lawyer_response_email(
            user_email="test@example.com",
            lawyer_name="Dr. Test Lawyer",
            case_summary_url="https://app.sumii.de/cases/123",
        )

    def test_send_verification_email_method_exists(self):
        """Test that EmailService has send_verification_email method"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        assert hasattr(email_service, "send_verification_email")
        assert callable(email_service.send_verification_email)

    def test_send_password_reset_email_method_exists(self):
        """Test that EmailService has send_password_reset_email method"""
        from app.services.email_service import EmailService

        email_service = EmailService()
        assert hasattr(email_service, "send_password_reset_email")
        assert callable(email_service.send_password_reset_email)
