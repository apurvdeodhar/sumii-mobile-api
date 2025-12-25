# Sumii v2 - Terraform Variables
# NO SECRETS IN THIS FILE - Use environment variables or AWS Secrets Manager

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment (local, dev, staging, prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["local", "dev", "staging", "prod"], var.environment)
    error_message = "Environment must be: local, dev, staging, or prod"
  }
}

# Feature Toggles
variable "enable_ecs" {
  description = "Enable ECS-related resources (IAM roles). Disable for local dev."
  type        = bool
  default     = false
}

variable "enable_notifications" {
  description = "Enable SNS/SQS notification infrastructure. Disable for local dev."
  type        = bool
  default     = false
}

variable "mistral_api_key" {
  description = "Mistral AI API key (sensitive)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "mistral_org_id" {
  description = "Mistral AI Organization ID (sensitive)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "mistral_library_id" {
  description = "Mistral AI Library ID (sensitive)"
  type        = string
  sensitive   = true
  default     = ""
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

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

variable "task_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 1
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
