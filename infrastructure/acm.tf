# ACM (AWS Certificate Manager) for SSL/TLS

# Request SSL certificate
resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = [
    "*.${var.domain_name}", # Wildcard for all subdomains
    "${var.api_subdomain}.${var.domain_name}",
    "anwalt.${var.domain_name}"
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${local.common_name}-ssl-cert"
  }
}

# Certificate validation (DNS)
resource "aws_acm_certificate_validation" "main" {
  certificate_arn = aws_acm_certificate.main.arn

  # Note: You'll need to add the DNS validation records to your domain's DNS
  # The records will be output after terraform apply

  timeouts {
    create = "45m"
  }
}

# Outputs
output "acm_certificate_arn" {
  value       = aws_acm_certificate.main.arn
  description = "ARN of ACM certificate for SSL/TLS"
}

output "acm_certificate_status" {
  value       = aws_acm_certificate.main.status
  description = "Status of ACM certificate"
}

output "acm_validation_options" {
  value = [
    for dvo in aws_acm_certificate.main.domain_validation_options : {
      domain_name           = dvo.domain_name
      resource_record_name  = dvo.resource_record_name
      resource_record_type  = dvo.resource_record_type
      resource_record_value = dvo.resource_record_value
    }
  ]
  description = "DNS validation records to add to your domain"
  sensitive   = false
}
