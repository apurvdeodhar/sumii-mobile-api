# SES (Simple Email Service) Configuration

# Domain Identity
resource "aws_ses_domain_identity" "main" {
  domain = var.domain_name
}

# Domain Verification (DNS TXT record)
resource "aws_ses_domain_identity_verification" "main" {
  domain = aws_ses_domain_identity.main.id

  depends_on = [aws_ses_domain_identity.main]
}

# DKIM Signing
resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# Email Identity for noreply
resource "aws_ses_email_identity" "noreply" {
  email = "noreply@${var.domain_name}"
}

# Configuration Set for tracking
resource "aws_ses_configuration_set" "main" {
  name = "${local.common_name}-ses-config"

  delivery_options {
    tls_policy = "Require"
  }

  reputation_metrics_enabled = true
}

# SNS Topic for bounce/complaint notifications
resource "aws_sns_topic" "ses_notifications" {
  name = "${local.common_name}-ses-notifications"

  tags = {
    Name = "${local.common_name}-ses-notifications"
  }
}

# SES Event Destination (bounces, complaints)
resource "aws_ses_event_destination" "sns" {
  name                   = "sns-destination"
  configuration_set_name = aws_ses_configuration_set.main.name
  enabled                = true
  matching_types         = ["bounce", "complaint", "reject"]

  sns_destination {
    topic_arn = aws_sns_topic.ses_notifications.arn
  }
}

# Outputs
output "ses_domain_identity" {
  value       = aws_ses_domain_identity.main.domain
  description = "SES domain identity"
}

output "ses_dkim_tokens" {
  value       = aws_ses_domain_dkim.main.dkim_tokens
  description = "DKIM tokens for DNS configuration"
  sensitive   = true
}

output "ses_configuration_set" {
  value       = aws_ses_configuration_set.main.name
  description = "SES configuration set name"
}
