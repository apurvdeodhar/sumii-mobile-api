# SES (Simple Email Service) Configuration
# Automated domain verification using Route53 (hosted in global-infra)
#
# IMPORTANT: SES Production Access
# ================================
# By default, new AWS accounts have SES in "sandbox" mode where you can only
# send to verified email addresses. To send to any email:
#
# 1. Request production access via AWS CLI:
#    aws sesv2 put-account-details \
#      --production-access-enabled \
#      --mail-type TRANSACTIONAL \
#      --website-url "https://sumii.de" \
#      --use-case-description "User registration, verification, and password reset emails for Sumii legal assistant mobile app" \
#      --region eu-central-1
#
# 2. Or via AWS Console: SES → Account dashboard → Request production access
#
# AWS typically approves within 24 hours for legitimate use cases.

# Look up the Route53 zone created by global-infra
data "aws_route53_zone" "main" {
  name = var.domain_name
}

# Domain Identity
resource "aws_ses_domain_identity" "main" {
  domain = var.domain_name
}

# DNS Record for SES Domain Verification (automated)
resource "aws_route53_record" "ses_verification" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "_amazonses.${var.domain_name}"
  type    = "TXT"
  ttl     = 600
  records = [aws_ses_domain_identity.main.verification_token]
}

# Domain Verification (waits for DNS propagation)
resource "aws_ses_domain_identity_verification" "main" {
  domain = aws_ses_domain_identity.main.id

  depends_on = [aws_route53_record.ses_verification]
}

# DKIM Signing
resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

# DNS Records for DKIM (automated)
resource "aws_route53_record" "ses_dkim" {
  count   = 3
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${aws_ses_domain_dkim.main.dkim_tokens[count.index]}._domainkey.${var.domain_name}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_ses_domain_dkim.main.dkim_tokens[count.index]}.dkim.amazonses.com"]
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
  name              = "${local.common_name}-ses-notifications"
  kms_master_key_id = "alias/aws/sns" # Use AWS managed key for encryption

  tags = {
    Name        = "${local.common_name}-ses-notifications"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
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
