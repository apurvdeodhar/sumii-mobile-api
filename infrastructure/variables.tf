# Sumii v2 - Terraform Variables
# NO SECRETS IN THIS FILE - Use environment variables or AWS Secrets Manager

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "sumii"
}

# Domain Configuration
variable "domain_name" {
  description = "Primary domain for SES and SSL"
  type        = string
  default     = "sumii.de"
}

variable "api_subdomain" {
  description = "API subdomain"
  type        = string
  default     = "api"
}

# Database Configuration (RDS - for production, use local PostgreSQL for MVP)
variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t4g.micro" # Free tier eligible
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "sumii_prod"
}

# S3 Configuration
variable "s3_pdf_bucket_name" {
  description = "S3 bucket for PDF storage"
  type        = string
  default     = "sumii-pdfs-prod"
}

variable "s3_documents_bucket_name" {
  description = "S3 bucket for document uploads"
  type        = string
  default     = "sumii-documents-prod"
}

# ECS Fargate Configuration
variable "ecs_task_cpu" {
  description = "CPU units for ECS task (256 = 0.25 vCPU)"
  type        = string
  default     = "256"
}

variable "ecs_task_memory" {
  description = "Memory for ECS task in MB"
  type        = string
  default     = "512"
}

variable "app_port" {
  description = "Application port"
  type        = number
  default     = 8000
}

# Tags
variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "Sumii"
    ManagedBy   = "Terraform"
    Environment = "dev"
  }
}
