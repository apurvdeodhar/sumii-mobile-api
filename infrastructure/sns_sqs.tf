# SNS Topics and SQS Queues for Async Notifications
# Only created when enable_notifications = true
#
# Architecture:
# - SNS Topic: Fanout hub for all notification events
# - SQS Queues: Async processing of push and email notifications
# - Push Delivery: Expo Push API (not AWS SNS Platform Apps)
# - Email Delivery: AWS SES

# SNS Topic for notification fanout
resource "aws_sns_topic" "notifications" {
  count             = var.enable_notifications ? 1 : 0
  name              = "${local.common_name}-notifications"
  kms_master_key_id = "alias/aws/sns" # Use AWS managed key for encryption

  tags = {
    Name        = "${local.common_name}-notifications"
    Description = "Fanout topic for all notifications"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

# DLQ for failed notifications
resource "aws_sqs_queue" "notification_dlq" {
  count                     = var.enable_notifications ? 1 : 0
  name                      = "${local.common_name}-notification-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true    # Enable server-side encryption

  tags = {
    Name        = "${local.common_name}-notification-dlq"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

# SQS Queue for push notifications (processed by backend, sent via Expo Push API)
resource "aws_sqs_queue" "push_notifications" {
  count                      = var.enable_notifications ? 1 : 0
  name                       = "${local.common_name}-push-notifications"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400 # 1 day
  receive_wait_time_seconds  = 10    # Long polling
  sqs_managed_sse_enabled    = true  # Enable server-side encryption

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq[0].arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${local.common_name}-push-notifications"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

# SQS Queue for email notifications (processed by backend, sent via SES)
resource "aws_sqs_queue" "email_notifications" {
  count                      = var.enable_notifications ? 1 : 0
  name                       = "${local.common_name}-email-notifications"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10
  sqs_managed_sse_enabled    = true # Enable server-side encryption

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq[0].arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "${local.common_name}-email-notifications"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}

# SQS Queue Policy - Allow SNS to send messages
resource "aws_sqs_queue_policy" "push_notifications" {
  count     = var.enable_notifications ? 1 : 0
  queue_url = aws_sqs_queue.push_notifications[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.push_notifications[0].arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.notifications[0].arn
        }
      }
    }]
  })
}

resource "aws_sqs_queue_policy" "email_notifications" {
  count     = var.enable_notifications ? 1 : 0
  queue_url = aws_sqs_queue.email_notifications[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.email_notifications[0].arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.notifications[0].arn
        }
      }
    }]
  })
}

# SNS Subscriptions (fanout to SQS)
resource "aws_sns_topic_subscription" "push_notifications" {
  count     = var.enable_notifications ? 1 : 0
  topic_arn = aws_sns_topic.notifications[0].arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.push_notifications[0].arn

  filter_policy = jsonencode({
    notification_type = ["push"]
  })
}

resource "aws_sns_topic_subscription" "email_notifications" {
  count     = var.enable_notifications ? 1 : 0
  topic_arn = aws_sns_topic.notifications[0].arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.email_notifications[0].arn

  filter_policy = jsonencode({
    notification_type = ["email"]
  })
}
