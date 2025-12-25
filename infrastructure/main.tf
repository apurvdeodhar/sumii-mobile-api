# Sumii v2 - Main Terraform Configuration
# Infrastructure: S3, IAM, SES, SNS, SQS, SSL

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Backend configuration - store state in S3 (created by sumii-global-infra/bootstrap)
  backend "s3" {
    bucket       = "sumii-mobile-api-tf-state"
    key          = "terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
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

# Locals
locals {
  account_id  = data.aws_caller_identity.current.account_id
  common_name = "sumii-mobile-api"
}
