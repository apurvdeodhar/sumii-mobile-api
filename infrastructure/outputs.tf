# Centralized outputs for sumii-mobile-api infrastructure
# All outputs in one file per terraform_standard_module_structure rule

################################################################################
# ECS Outputs
################################################################################

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = var.enable_ecs ? aws_ecs_service.mobile_api[0].name : null
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = var.enable_ecs ? aws_ecs_task_definition.mobile_api[0].arn : null
}

output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = var.enable_ecs ? aws_iam_role.ecs_task_execution_role[0].arn : null
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  value       = var.enable_ecs ? aws_iam_role.ecs_task_role[0].arn : null
}

################################################################################
# RDS Outputs
################################################################################

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = var.enable_ecs ? module.rds[0].db_instance_endpoint : null
}

output "rds_db_name" {
  description = "RDS database name"
  value       = var.enable_ecs ? module.rds[0].db_instance_name : null
}

################################################################################
# S3 Outputs
################################################################################

output "pdf_bucket_name" {
  description = "Name of the PDF S3 bucket"
  value       = aws_s3_bucket.pdfs[local.s3_env].id
}

output "pdf_bucket_arn" {
  description = "ARN of the PDF S3 bucket"
  value       = aws_s3_bucket.pdfs[local.s3_env].arn
}

output "documents_bucket_name" {
  description = "Name of the documents S3 bucket"
  value       = aws_s3_bucket.documents[local.s3_env].id
}

output "documents_bucket_arn" {
  description = "ARN of the documents S3 bucket"
  value       = aws_s3_bucket.documents[local.s3_env].arn
}

################################################################################
# Secrets Outputs
################################################################################

output "jwt_secret_arn" {
  description = "ARN of JWT secret in Secrets Manager"
  value       = var.enable_ecs ? aws_secretsmanager_secret.jwt_secret[0].arn : null
  sensitive   = true
}

output "mistral_api_key_arn" {
  description = "ARN of Mistral API key in Secrets Manager"
  value       = var.enable_ecs ? aws_secretsmanager_secret.mistral_api_key[0].arn : null
  sensitive   = true
}

################################################################################
# SES Outputs
################################################################################

output "ses_domain_identity" {
  description = "SES domain identity"
  value       = aws_ses_domain_identity.main.domain
}

output "ses_dkim_tokens" {
  description = "DKIM tokens for SES domain"
  value       = aws_ses_domain_dkim.main.dkim_tokens
  sensitive   = true
}

output "ses_configuration_set" {
  description = "SES configuration set name"
  value       = aws_ses_configuration_set.main.name
}

################################################################################
# SNS/SQS Outputs
################################################################################

output "sns_notifications_topic_arn" {
  description = "ARN of the SNS notifications topic"
  value       = var.enable_notifications ? aws_sns_topic.notifications[0].arn : null
}

output "push_notifications_queue_url" {
  description = "URL of the push notifications SQS queue"
  value       = var.enable_notifications ? aws_sqs_queue.push_notifications[0].url : null
}

output "email_notifications_queue_url" {
  description = "URL of the email notifications SQS queue"
  value       = var.enable_notifications ? aws_sqs_queue.email_notifications[0].url : null
}
