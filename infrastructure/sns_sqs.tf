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
  count = var.enable_notifications ? 1 : 0
  name  = "${local.common_name}-notifications"

  tags = {
    Name        = "${local.common_name}-notifications"
    Description = "Fanout topic for all notifications"
  }
}

# DLQ for failed notifications
resource "aws_sqs_queue" "notification_dlq" {
  count                     = var.enable_notifications ? 1 : 0
  name                      = "${local.common_name}-notification-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "${local.common_name}-notification-dlq"
  }
}

# SQS Queue for push notifications (processed by backend, sent via Expo Push API)
resource "aws_sqs_queue" "push_notifications" {
  count                      = var.enable_notifications ? 1 : 0
  name                       = "${local.common_name}-push-notifications"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400 # 1 day
  receive_wait_time_seconds  = 10    # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq[0].arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${local.common_name}-push-notifications"
  }
}

# SQS Queue for email notifications (processed by backend, sent via SES)
resource "aws_sqs_queue" "email_notifications" {
  count                      = var.enable_notifications ? 1 : 0
  name                       = "${local.common_name}-email-notifications"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq[0].arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${local.common_name}-email-notifications"
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

# Outputs (conditional)
output "sns_notifications_topic_arn" {
  value       = var.enable_notifications ? aws_sns_topic.notifications[0].arn : null
  description = "ARN of SNS notifications topic"
}

output "push_notifications_queue_url" {
  value       = var.enable_notifications ? aws_sqs_queue.push_notifications[0].url : null
  description = "URL of push notifications SQS queue"
}

output "email_notifications_queue_url" {
  value       = var.enable_notifications ? aws_sqs_queue.email_notifications[0].url : null
  description = "URL of email notifications SQS queue"
}
