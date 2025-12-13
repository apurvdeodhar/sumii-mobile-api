# Sumii v2 - Main OpenTofu Configuration
# 48-Hour MVP Infrastructure: S3, IAM, SES, SNS, SQS, SSL

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration - store state in S3
  backend "s3" {
    bucket         = "sumii-tofu-state" # Create this manually first
    key            = "sumii-v2/tofu.tfstate"
    region         = "eu-central-1"
    encrypt        = true
    dynamodb_table = "sumii-tofu-locks" # For state locking
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# Locals
locals {
  account_id  = data.aws_caller_identity.current.account_id
  common_name = "${var.project_name}-${var.environment}"
}
