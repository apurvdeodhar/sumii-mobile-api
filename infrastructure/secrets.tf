# Application Secrets for sumii-mobile-api
# Only created when enable_ecs = true

# Database URL Secret (constructed from local RDS endpoint and password)
resource "aws_secretsmanager_secret" "database_url" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/database-url-v2"
  description             = "PostgreSQL connection string for sumii-mobile-api"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-database-url"
  }
}

resource "aws_secretsmanager_secret_version" "database_url" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.database_url[0].id
  secret_string = "postgresql+asyncpg://postgres:${random_password.db_password[0].result}@${split(":", module.rds[0].db_instance_endpoint)[0]}:5432/sumii_prod"
}

# JWT Secret (auto-generated)
resource "random_password" "jwt_secret" {
  count   = var.enable_ecs ? 1 : 0
  length  = 64
  special = false # Simpler chars for JWT secret
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/jwt-secret"
  description             = "JWT signing secret for sumii-mobile-api"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.jwt_secret[0].id
  secret_string = random_password.jwt_secret[0].result
}

# Mistral API Key
resource "aws_secretsmanager_secret" "mistral_api_key" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/mistral-api-key"
  description             = "Mistral AI API key for sumii-mobile-api"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-mistral-api-key"
  }
}

resource "aws_secretsmanager_secret_version" "mistral_api_key" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.mistral_api_key[0].id
  secret_string = var.mistral_api_key
}

# Mistral Org ID
resource "aws_secretsmanager_secret" "mistral_org_id" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/mistral-org-id"
  description             = "Mistral AI Organization ID for sumii-mobile-api"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-mistral-org-id"
  }
}

resource "aws_secretsmanager_secret_version" "mistral_org_id" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.mistral_org_id[0].id
  secret_string = var.mistral_org_id
}

# Mistral Library ID
resource "aws_secretsmanager_secret" "mistral_library_id" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/mistral-library-id"
  description             = "Mistral AI Library ID for sumii-mobile-api"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-mistral-library-id"
  }
}

resource "aws_secretsmanager_secret_version" "mistral_library_id" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.mistral_library_id[0].id
  secret_string = var.mistral_library_id
}
