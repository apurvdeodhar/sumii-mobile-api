# S3 Buckets for PDFs and Documents

# PDF Storage Bucket (environment-specific naming)
resource "aws_s3_bucket" "pdfs" {
  bucket = var.s3_pdf_bucket_name != "" ? var.s3_pdf_bucket_name : "${local.common_name}-pdfs"

  tags = {
    Name        = "${local.common_name}-pdfs"
    Description = "Legal summary PDFs"
  }
}

# PDF Bucket Versioning
resource "aws_s3_bucket_versioning" "pdfs" {
  bucket = aws_s3_bucket.pdfs.id

  versioning_configuration {
    status = "Enabled"
  }
}

# PDF Bucket Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "pdfs" {
  bucket = aws_s3_bucket.pdfs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# PDF Bucket Lifecycle (delete after 30 days for MVP)
resource "aws_s3_bucket_lifecycle_configuration" "pdfs" {
  bucket = aws_s3_bucket.pdfs.id

  rule {
    id     = "delete-old-pdfs"
    status = "Enabled"

    expiration {
      days = 30
    }
  }
}

# PDF Bucket CORS (for direct downloads from mobile app)
resource "aws_s3_bucket_cors_configuration" "pdfs" {
  bucket = aws_s3_bucket.pdfs.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["https://${var.domain_name}", "https://*.${var.domain_name}"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Document Upload Bucket (environment-specific naming)
resource "aws_s3_bucket" "documents" {
  bucket = var.s3_documents_bucket_name != "" ? var.s3_documents_bucket_name : "${local.common_name}-documents"

  tags = {
    Name        = "${local.common_name}-documents"
    Description = "User uploaded documents"
  }
}

# Document Bucket Versioning
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Document Bucket Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Document Bucket Lifecycle
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "delete-old-documents"
    status = "Enabled"

    expiration {
      days = 90 # Keep documents longer than PDFs
    }
  }
}

# Outputs
output "pdf_bucket_name" {
  value       = aws_s3_bucket.pdfs.id
  description = "Name of S3 bucket for PDFs"
}

output "pdf_bucket_arn" {
  value       = aws_s3_bucket.pdfs.arn
  description = "ARN of S3 bucket for PDFs"
}

output "documents_bucket_name" {
  value       = aws_s3_bucket.documents.id
  description = "Name of S3 bucket for documents"
}

output "documents_bucket_arn" {
  value       = aws_s3_bucket.documents.arn
  description = "ARN of S3 bucket for documents"
}
