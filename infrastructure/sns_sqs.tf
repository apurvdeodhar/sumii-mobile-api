# SNS Topics and SQS Queues for Notifications

# SNS Topic for push notifications (iOS/Android)
resource "aws_sns_platform_application" "ios" {
  name                = "${local.common_name}-ios-push"
  platform            = "APNS" # Apple Push Notification Service
  platform_credential = ""     # Set via AWS Console or Secrets Manager (APNs certificate)

  # Production endpoint
  platform_principal = "" # Set via AWS Console or Secrets Manager

  lifecycle {
    ignore_changes = [platform_credential, platform_principal]
  }
}

resource "aws_sns_platform_application" "android" {
  name                = "${local.common_name}-android-push"
  platform            = "GCM" # Google Cloud Messaging (Firebase)
  platform_credential = ""    # Set via AWS Console or Secrets Manager (FCM server key)

  lifecycle {
    ignore_changes = [platform_credential]
  }
}

# SNS Topic for notification fanout
resource "aws_sns_topic" "notifications" {
  name = "${local.common_name}-notifications"

  tags = {
    Name        = "${local.common_name}-notifications"
    Description = "Fanout topic for all notifications"
  }
}

# DLQ for failed notifications
resource "aws_sqs_queue" "notification_dlq" {
  name                      = "${local.common_name}-notification-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Name = "${local.common_name}-notification-dlq"
  }
}

# SQS Queue for push notifications
resource "aws_sqs_queue" "push_notifications" {
  name                       = "${local.common_name}-push-notifications"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400 # 1 day
  receive_wait_time_seconds  = 10    # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${local.common_name}-push-notifications"
  }
}

# SQS Queue for email notifications
resource "aws_sqs_queue" "email_notifications" {
  name                       = "${local.common_name}-email-notifications"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notification_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${local.common_name}-email-notifications"
  }
}

# SQS Queue Policy - Allow SNS to send messages
resource "aws_sqs_queue_policy" "push_notifications" {
  queue_url = aws_sqs_queue.push_notifications.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.push_notifications.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.notifications.arn
        }
      }
    }]
  })
}

resource "aws_sqs_queue_policy" "email_notifications" {
  queue_url = aws_sqs_queue.email_notifications.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sns.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.email_notifications.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.notifications.arn
        }
      }
    }]
  })
}

# SNS Subscriptions (fanout to SQS)
resource "aws_sns_topic_subscription" "push_notifications" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.push_notifications.arn

  filter_policy = jsonencode({
    notification_type = ["push"]
  })
}

resource "aws_sns_topic_subscription" "email_notifications" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.email_notifications.arn

  filter_policy = jsonencode({
    notification_type = ["email"]
  })
}

# Outputs
output "sns_notifications_topic_arn" {
  value       = aws_sns_topic.notifications.arn
  description = "ARN of SNS notifications topic"
}

output "push_notifications_queue_url" {
  value       = aws_sqs_queue.push_notifications.url
  description = "URL of push notifications SQS queue"
}

output "email_notifications_queue_url" {
  value       = aws_sqs_queue.email_notifications.url
  description = "URL of email notifications SQS queue"
}

output "sns_ios_application_arn" {
  value       = aws_sns_platform_application.ios.arn
  description = "ARN of iOS SNS platform application"
}

output "sns_android_application_arn" {
  value       = aws_sns_platform_application.android.arn
  description = "ARN of Android SNS platform application"
}
