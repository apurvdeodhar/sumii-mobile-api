# ECS Task Definition and Service for sumii-mobile-api
# Only created when enable_ecs = true

# Data sources for global infrastructure
data "aws_ssm_parameter" "cluster_name" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/ecs/cluster_name"
}

data "aws_ssm_parameter" "ecr_url" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/ecr/sumii-mobile-api"
}

data "aws_ssm_parameter" "target_group_arn" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/alb/public/target-group/mobile-api/arn"
}

data "aws_ssm_parameter" "security_group_id" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/security-group/mobile-api/id"
}

data "aws_ssm_parameter" "private_subnets" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/vpc/private_subnets"
}

data "aws_ssm_parameter" "vpc_id" {
  count = var.enable_ecs ? 1 : 0
  name  = "/sumii/global/vpc/id"
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "mobile_api" {
  count             = var.enable_ecs ? 1 : 0
  name              = "/ecs/${local.common_name}"
  retention_in_days = 14

  tags = {
    Name = "${local.common_name}-logs"
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "mobile_api" {
  count                    = var.enable_ecs ? 1 : 0
  family                   = local.common_name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role[0].arn
  task_role_arn            = aws_iam_role.ecs_task_role[0].arn

  container_definitions = jsonencode([{
    name      = local.common_name
    image     = "${data.aws_ssm_parameter.ecr_url[0].value}:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = var.app_port
      protocol      = "tcp"
    }]

    environment = [
      { name = "ENVIRONMENT", value = var.environment },
      { name = "PORT", value = tostring(var.app_port) },
      { name = "DB_HOST", value = split(":", module.rds[0].db_instance_endpoint)[0] },
      { name = "S3_BUCKET", value = aws_s3_bucket.pdfs[local.s3_env].id },
      { name = "S3_DOCUMENTS_BUCKET", value = aws_s3_bucket.documents[local.s3_env].id },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "CORS_ORIGINS", value = "*" },
      { name = "ANWALT_API_BASE_URL", value = "https://internal.anwalt.sumii.de" },
      { name = "FRONTEND_URL", value = "https://app.sumii.de" },
    ]

    secrets = [
      {
        name      = "DATABASE_URL"
        valueFrom = aws_secretsmanager_secret.database_url[0].arn
      },
      {
        name      = "MISTRAL_API_KEY"
        valueFrom = aws_secretsmanager_secret.mistral_api_key[0].arn
      },
      {
        name      = "MISTRAL_ORG_ID"
        valueFrom = aws_secretsmanager_secret.mistral_org_id[0].arn
      },
      {
        name      = "MISTRAL_LIBRARY_ID"
        valueFrom = aws_secretsmanager_secret.mistral_library_id[0].arn
      },
      {
        name      = "SECRET_KEY"
        valueFrom = aws_secretsmanager_secret.jwt_secret[0].arn
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.mobile_api[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.app_port}/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Name = "${local.common_name}-task-definition"
  }
}

# ECS Service
resource "aws_ecs_service" "mobile_api" {
  count           = var.enable_ecs ? 1 : 0
  name            = local.common_name
  cluster         = data.aws_ssm_parameter.cluster_name[0].value
  task_definition = aws_ecs_task_definition.mobile_api[0].arn
  desired_count   = var.task_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = split(",", data.aws_ssm_parameter.private_subnets[0].value)
    security_groups  = [data.aws_ssm_parameter.security_group_id[0].value]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = data.aws_ssm_parameter.target_group_arn[0].value
    container_name   = local.common_name
    container_port   = var.app_port
  }

  # Allow external changes without Terraform plan difference
  lifecycle {
    ignore_changes = [desired_count]
  }

  tags = {
    Name = "${local.common_name}-service"
  }
}
