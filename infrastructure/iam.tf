# IAM Roles and Policies for ECS Fargate and Application

# ECS Task Execution Role (for pulling images, logging)
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${local.common_name}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${local.common_name}-ecs-execution-role"
  }
}

# Attach AWS managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow ECS to read secrets from Secrets Manager
resource "aws_iam_role_policy" "ecs_secrets_policy" {
  name = "${local.common_name}-ecs-secrets-policy"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "kms:Decrypt"
      ]
      Resource = [
        "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${var.project_name}/*",
        "arn:aws:kms:${var.aws_region}:${local.account_id}:key/*"
      ]
    }]
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task_role" {
  name = "${local.common_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${local.common_name}-ecs-task-role"
  }
}

# S3 Access Policy for Task Role
resource "aws_iam_role_policy" "s3_access_policy" {
  name = "${local.common_name}-s3-access-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${aws_s3_bucket.pdfs.arn}",
          "${aws_s3_bucket.pdfs.arn}/*",
          "${aws_s3_bucket.documents.arn}",
          "${aws_s3_bucket.documents.arn}/*"
        ]
      }
    ]
  })
}

# SES Send Email Policy
resource "aws_iam_role_policy" "ses_send_policy" {
  name = "${local.common_name}-ses-send-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ]
      Resource = "*"
      Condition = {
        StringEquals = {
          "ses:FromAddress" = "noreply@${var.domain_name}"
        }
      }
    }]
  })
}

# SNS Publish Policy (for push notifications)
resource "aws_iam_role_policy" "sns_publish_policy" {
  name = "${local.common_name}-sns-publish-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sns:Publish",
        "sns:CreatePlatformEndpoint",
        "sns:DeleteEndpoint",
        "sns:GetEndpointAttributes",
        "sns:SetEndpointAttributes"
      ]
      Resource = "arn:aws:sns:${var.aws_region}:${local.account_id}:*"
    }]
  })
}

# SQS Access Policy (for notification queue)
resource "aws_iam_role_policy" "sqs_access_policy" {
  name = "${local.common_name}-sqs-access-policy"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:SendMessage",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ]
      Resource = "arn:aws:sqs:${var.aws_region}:${local.account_id}:${var.project_name}-*"
    }]
  })
}

# Outputs
output "ecs_task_execution_role_arn" {
  value       = aws_iam_role.ecs_task_execution_role.arn
  description = "ARN of ECS task execution role"
}

output "ecs_task_role_arn" {
  value       = aws_iam_role.ecs_task_role.arn
  description = "ARN of ECS task role"
}
