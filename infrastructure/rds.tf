# RDS PostgreSQL for sumii-mobile-api
# Managed directly in this stack to avoid cross-stack password sync issues

# Generate a simple alphanumeric password
resource "random_password" "db_password" {
  count   = var.enable_ecs ? 1 : 0
  length  = 32
  special = false # Alphanumeric only for URL compatibility
}

# Store password in Secrets Manager
resource "aws_secretsmanager_secret" "db_password" {
  count                   = var.enable_ecs ? 1 : 0
  name                    = "${var.project_name}/mobile-api/db-password-v2"
  description             = "PostgreSQL password for sumii-mobile-api RDS"
  recovery_window_in_days = 7

  tags = {
    Name = "${local.common_name}-db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  count         = var.enable_ecs ? 1 : 0
  secret_id     = aws_secretsmanager_secret.db_password[0].id
  secret_string = random_password.db_password[0].result
}

# RDS Security Group - allows access from ECS tasks
module "rds_security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "~> 5.0"
  count   = var.enable_ecs ? 1 : 0

  name   = "${local.common_name}-rds-sg"
  vpc_id = data.aws_ssm_parameter.vpc_id[0].value

  ingress_with_source_security_group_id = [
    {
      from_port                = 5432
      to_port                  = 5432
      protocol                 = "tcp"
      source_security_group_id = data.aws_ssm_parameter.security_group_id[0].value
    }
  ]

  tags = {
    Name = "${local.common_name}-rds-sg"
  }
}

# RDS Instance
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 5.0"
  count   = var.enable_ecs ? 1 : 0

  identifier             = "sumii-mobile-api-db-v2"
  engine                 = "postgres"
  engine_version         = "14"
  family                 = "postgres14"
  major_engine_version   = "14"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "sumii_prod"
  username               = "postgres"
  password               = random_password.db_password[0].result
  port                   = 5432
  vpc_security_group_ids = [module.rds_security_group[0].security_group_id]
  create_db_subnet_group = true
  subnet_ids             = split(",", data.aws_ssm_parameter.private_subnets[0].value)
  skip_final_snapshot    = true
  publicly_accessible    = false

  tags = {
    Name        = "${local.common_name}-rds"
    Environment = var.environment
    Terraform   = "true"
    Application = "sumii-mobile-api"
  }
}
