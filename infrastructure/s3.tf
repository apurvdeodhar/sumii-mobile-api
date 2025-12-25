# S3 Buckets for PDFs and Documents
# Creates buckets for all environments so they coexist

locals {
  # Environments to create buckets for
  s3_environments = toset(["local", "prod"])
}

################################################################################
# PDF Storage Buckets
################################################################################
resource "aws_s3_bucket" "pdfs" {
  for_each = local.s3_environments
  bucket   = "${var.project_name}-${each.key}-pdfs"

  tags = {
    Name        = "${var.project_name}-${each.key}-pdfs"
    Description = "Legal summary PDFs"
    Environment = each.key
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

resource "aws_s3_bucket_versioning" "pdfs" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.pdfs[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "pdfs" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.pdfs[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pdfs" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.pdfs[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "pdfs" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.pdfs[each.key].id

  rule {
    id     = "delete-old-pdfs"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }

    # Abort incomplete multipart uploads (CKV_AWS_300)
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "pdfs" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.pdfs[each.key].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://${var.domain_name}", "https://*.${var.domain_name}"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

################################################################################
# Document Upload Buckets
################################################################################
resource "aws_s3_bucket" "documents" {
  for_each = local.s3_environments
  bucket   = "${var.project_name}-${each.key}-documents"

  tags = {
    Name        = "${var.project_name}-${each.key}-documents"
    Description = "User uploaded documents"
    Environment = each.key
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.documents[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.documents[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.documents[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  for_each = local.s3_environments
  bucket   = aws_s3_bucket.documents[each.key].id

  rule {
    id     = "delete-old-documents"
    status = "Enabled"

    filter {}

    expiration {
      days = 90 # Keep documents longer than PDFs
    }

    # Abort incomplete multipart uploads (CKV_AWS_300)
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

################################################################################
# Outputs - Current environment buckets
################################################################################

# Map environment to S3 bucket environment (dev/staging uses local buckets)
locals {
  s3_env = var.environment == "prod" ? "prod" : "local"
}
