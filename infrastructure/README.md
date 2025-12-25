# Sumii v2 - Terraform Infrastructure

## Overview

This Terraform configuration sets up AWS infrastructure for Sumii v2:

- **S3**: PDF storage and document uploads
- **IAM**: Roles and policies for ECS Fargate
- **SES**: Email notifications (noreply@sumii.de)
- **SNS/SQS**: Push notification fanout
- **ACM**: SSL/TLS certificates
- **VPC**: Network infrastructure (optional for MVP, use default VPC)
- **ECS Fargate**: Container orchestration (configured separately)

## Prerequisites

1. **AWS CLI configured**:

   ```bash
   aws configure
   # Enter: AWS Access Key ID, Secret Access Key, Region (eu-central-1)
   ```

2. **Terraform installed** (v1.6+):

   ```bash
   # macOS
   brew install terraform

   # Linux
   curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
   sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
   sudo apt-get update && sudo apt-get install terraform

   # Verify installation
   terraform version
   ```

3. **S3 bucket for Terraform state** (create manually first):
   ```bash
   aws s3 mb s3://sumii-terraform-state --region eu-central-1
   aws dynamodb create-table \
     --table-name sumii-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region eu-central-1
   ```

## 🚀 Usage

### Environment Toggle

The `environment` variable supports: `local`, `dev`, `staging`, `prod`

```bash
# Local development
terraform apply -var="environment=local"

# Development
terraform apply -var="environment=dev"

# Production
terraform apply -var="environment=prod"
```

### 1. Initialize Terraform

```bash
cd infrastructure
terraform init
```

### 2. Review Configuration

```bash
# Check variables
cat variables.tf

# Customize if needed (create terraform.tfvars)
cat > terraform.tfvars <<EOF
environment = "local"
domain_name = "sumii.de"
aws_region  = "eu-central-1"
EOF
```

### 3. Plan Infrastructure

```bash
terraform plan -out=tfplan
```

Review the plan carefully before applying!

### 4. Apply Infrastructure

```bash
terraform apply tfplan
```

This will create:

- S3 buckets: `sumii-{environment}-pdfs`, `sumii-{environment}-documents`
- IAM roles for ECS Fargate
- SES domain identity for `sumii.de`
- SNS/SQS for notifications
- ACM certificate for SSL

### 5. Configure DNS Records

After `terraform apply`, you'll get outputs for DNS configuration:

```bash
terraform output acm_validation_options
terraform output ses_dkim_tokens
```

Add these records to your domain's DNS (sumii.de):

**For ACM (SSL validation)**:

```
Type: CNAME
Name: _xxxxx.sumii.de
Value: _xxxxx.acm-validations.aws
```

**For SES (email sending)**:

```
Type: TXT
Name: sumii.de
Value: "v=spf1 include:amazonses.com ~all"

Type: CNAME (3 records, one for each DKIM token)
Name: token1._domainkey.sumii.de
Value: token1.dkim.amazonses.com
```

### 6. Verify Resources

```bash
# List S3 buckets
aws s3 ls | grep sumii

# Check IAM roles
aws iam list-roles | grep sumii

# Verify SES domain
aws ses get-identity-verification-attributes --identities sumii.de

# Check SNS topics
aws sns list-topics | grep sumii
```

## 📁 File Structure

```
infrastructure/
├── main.tf           # Provider and backend configuration
├── variables.tf      # Input variables (NO SECRETS!)
├── s3.tf             # S3 buckets for PDFs and documents
├── iam.tf            # IAM roles and policies
├── ses.tf            # SES email configuration
├── sns_sqs.tf        # SNS topics and SQS queues
├── acm.tf            # SSL/TLS certificates
└── README.md         # This file
```

## 🔒 Security Best Practices

### NO HARDCODED SECRETS

**NEVER commit:**

- AWS credentials
- API keys
- Certificates
- Private keys

**Use instead:**

- AWS Secrets Manager
- Environment variables
- IAM roles (no keys needed for ECS)

### Secrets Manager Setup

```bash
# Store Mistral AI key
aws secretsmanager create-secret \
  --name sumii/mistral-api-key \
  --secret-string "your-mistral-key" \
  --region eu-central-1

# Store JWT secret
aws secretsmanager create-secret \
  --name sumii/jwt-secret \
  --secret-string "$(openssl rand -base64 32)" \
  --region eu-central-1

# Store database password
aws secretsmanager create-secret \
  --name sumii/db-password \
  --secret-string "$(openssl rand -base64 24)" \
  --region eu-central-1
```

## 💰 Cost Estimation

```
S3 storage:           ~$0.023/GB/month
SES emails:           $0.10 per 1,000 emails
SNS push:             $0.50 per 1M requests
SQS:                  $0.40 per 1M requests
ACM certificates:     FREE
Data transfer:        $0.09/GB (out to internet)

Estimated local dev:  ~$2-5/month
```

## 🧹 Cleanup

To destroy all resources:

```bash
# WARNING: This deletes EVERYTHING
terraform destroy

# Confirm by typing 'yes'
```

## 🆘 Troubleshooting

### Issue: State lock error

```bash
# Release lock (if terraform crashed)
terraform force-unlock LOCK_ID
```

### Issue: Certificate validation stuck

```
# Check DNS records are correct
dig _xxxxx.sumii.de CNAME

# Wait up to 45 minutes for validation
```

### Issue: SES in sandbox mode

```bash
# Request production access via AWS Console
# Or test with verified email addresses only
aws ses verify-email-identity --email-address your-dev@email.com
```

## 📚 Resources

- [Terraform Docs](https://developer.hashicorp.com/terraform/docs)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS ECS Fargate Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/intro.html)

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.6 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | ~> 5.0 |
| <a name="requirement_random"></a> [random](#requirement\_random) | ~> 3.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 5.100.0 |
| <a name="provider_random"></a> [random](#provider\_random) | 3.7.2 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_rds"></a> [rds](#module\_rds) | terraform-aws-modules/rds/aws | ~> 5.0 |
| <a name="module_rds_security_group"></a> [rds\_security\_group](#module\_rds\_security\_group) | terraform-aws-modules/security-group/aws | ~> 5.0 |

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_log_group.mobile_api](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_group) | resource |
| [aws_ecs_service.mobile_api](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service) | resource |
| [aws_ecs_task_definition.mobile_api](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_task_definition) | resource |
| [aws_iam_role.ecs_task_execution_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role.ecs_task_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role) | resource |
| [aws_iam_role_policy.ecs_secrets_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.s3_access_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.ses_send_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.sns_publish_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy.sqs_access_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy) | resource |
| [aws_iam_role_policy_attachment.ecs_task_execution_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy_attachment) | resource |
| [aws_route53_record.ses_dkim](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route53_record) | resource |
| [aws_route53_record.ses_verification](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route53_record) | resource |
| [aws_s3_bucket.documents](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket) | resource |
| [aws_s3_bucket_cors_configuration.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_cors_configuration) | resource |
| [aws_s3_bucket_lifecycle_configuration.documents](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_s3_bucket_lifecycle_configuration.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_lifecycle_configuration) | resource |
| [aws_s3_bucket_public_access_block.documents](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_bucket_public_access_block.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block) | resource |
| [aws_s3_bucket_server_side_encryption_configuration.documents](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_server_side_encryption_configuration) | resource |
| [aws_s3_bucket_server_side_encryption_configuration.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_server_side_encryption_configuration) | resource |
| [aws_s3_bucket_versioning.documents](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_versioning) | resource |
| [aws_s3_bucket_versioning.pdfs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_versioning) | resource |
| [aws_secretsmanager_secret.database_url](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.db_password](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.jwt_secret](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.mistral_api_key](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.mistral_library_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret.mistral_org_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret) | resource |
| [aws_secretsmanager_secret_version.database_url](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.db_password](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.jwt_secret](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.mistral_api_key](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.mistral_library_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_secretsmanager_secret_version.mistral_org_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/secretsmanager_secret_version) | resource |
| [aws_ses_configuration_set.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_configuration_set) | resource |
| [aws_ses_domain_dkim.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_domain_dkim) | resource |
| [aws_ses_domain_identity.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_domain_identity) | resource |
| [aws_ses_domain_identity_verification.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_domain_identity_verification) | resource |
| [aws_ses_email_identity.noreply](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_email_identity) | resource |
| [aws_ses_event_destination.sns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ses_event_destination) | resource |
| [aws_sns_topic.notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_sns_topic.ses_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_sns_topic_subscription.email_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic_subscription) | resource |
| [aws_sns_topic_subscription.push_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic_subscription) | resource |
| [aws_sqs_queue.email_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue) | resource |
| [aws_sqs_queue.notification_dlq](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue) | resource |
| [aws_sqs_queue.push_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue) | resource |
| [aws_sqs_queue_policy.email_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue_policy) | resource |
| [aws_sqs_queue_policy.push_notifications](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sqs_queue_policy) | resource |
| [random_password.db_password](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/password) | resource |
| [random_password.jwt_secret](https://registry.terraform.io/providers/hashicorp/random/latest/docs/resources/password) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_route53_zone.main](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/route53_zone) | data source |
| [aws_ssm_parameter.cluster_name](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.ecr_url](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.private_subnets](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.security_group_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.target_group_arn](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |
| [aws_ssm_parameter.vpc_id](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ssm_parameter) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_app_port"></a> [app\_port](#input\_app\_port) | Application port | `number` | `8000` | no |
| <a name="input_aws_region"></a> [aws\_region](#input\_aws\_region) | AWS region for all resources | `string` | `"eu-central-1"` | no |
| <a name="input_domain_name"></a> [domain\_name](#input\_domain\_name) | Primary domain for SES and SSL | `string` | `"sumii.de"` | no |
| <a name="input_ecs_task_cpu"></a> [ecs\_task\_cpu](#input\_ecs\_task\_cpu) | CPU units for ECS task (256 = 0.25 vCPU) | `string` | `"256"` | no |
| <a name="input_ecs_task_memory"></a> [ecs\_task\_memory](#input\_ecs\_task\_memory) | Memory for ECS task in MB | `string` | `"512"` | no |
| <a name="input_enable_ecs"></a> [enable\_ecs](#input\_enable\_ecs) | Enable ECS-related resources (IAM roles). Disable for local dev. | `bool` | `false` | no |
| <a name="input_enable_notifications"></a> [enable\_notifications](#input\_enable\_notifications) | Enable SNS/SQS notification infrastructure. Disable for local dev. | `bool` | `false` | no |
| <a name="input_environment"></a> [environment](#input\_environment) | Environment (local, dev, staging, prod) | `string` | `"dev"` | no |
| <a name="input_image_tag"></a> [image\_tag](#input\_image\_tag) | Docker image tag to deploy | `string` | `"latest"` | no |
| <a name="input_mistral_api_key"></a> [mistral\_api\_key](#input\_mistral\_api\_key) | Mistral AI API key (sensitive) | `string` | `""` | no |
| <a name="input_mistral_library_id"></a> [mistral\_library\_id](#input\_mistral\_library\_id) | Mistral AI Library ID (sensitive) | `string` | `""` | no |
| <a name="input_mistral_org_id"></a> [mistral\_org\_id](#input\_mistral\_org\_id) | Mistral AI Organization ID (sensitive) | `string` | `""` | no |
| <a name="input_project_name"></a> [project\_name](#input\_project\_name) | Project name for resource naming | `string` | `"sumii"` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Common tags for all resources | `map(string)` | <pre>{<br/>  "Environment": "dev",<br/>  "ManagedBy": "Terraform",<br/>  "Project": "Sumii"<br/>}</pre> | no |
| <a name="input_task_count"></a> [task\_count](#input\_task\_count) | Number of ECS tasks to run | `number` | `1` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_documents_bucket_arn"></a> [documents\_bucket\_arn](#output\_documents\_bucket\_arn) | ARN of the documents S3 bucket |
| <a name="output_documents_bucket_name"></a> [documents\_bucket\_name](#output\_documents\_bucket\_name) | Name of the documents S3 bucket |
| <a name="output_ecs_service_name"></a> [ecs\_service\_name](#output\_ecs\_service\_name) | Name of the ECS service |
| <a name="output_ecs_task_definition_arn"></a> [ecs\_task\_definition\_arn](#output\_ecs\_task\_definition\_arn) | ARN of the ECS task definition |
| <a name="output_ecs_task_execution_role_arn"></a> [ecs\_task\_execution\_role\_arn](#output\_ecs\_task\_execution\_role\_arn) | ARN of ECS task execution role |
| <a name="output_ecs_task_role_arn"></a> [ecs\_task\_role\_arn](#output\_ecs\_task\_role\_arn) | ARN of ECS task role |
| <a name="output_email_notifications_queue_url"></a> [email\_notifications\_queue\_url](#output\_email\_notifications\_queue\_url) | URL of the email notifications SQS queue |
| <a name="output_jwt_secret_arn"></a> [jwt\_secret\_arn](#output\_jwt\_secret\_arn) | ARN of JWT secret in Secrets Manager |
| <a name="output_mistral_api_key_arn"></a> [mistral\_api\_key\_arn](#output\_mistral\_api\_key\_arn) | ARN of Mistral API key in Secrets Manager |
| <a name="output_pdf_bucket_arn"></a> [pdf\_bucket\_arn](#output\_pdf\_bucket\_arn) | ARN of the PDF S3 bucket |
| <a name="output_pdf_bucket_name"></a> [pdf\_bucket\_name](#output\_pdf\_bucket\_name) | Name of the PDF S3 bucket |
| <a name="output_push_notifications_queue_url"></a> [push\_notifications\_queue\_url](#output\_push\_notifications\_queue\_url) | URL of the push notifications SQS queue |
| <a name="output_rds_db_name"></a> [rds\_db\_name](#output\_rds\_db\_name) | RDS database name |
| <a name="output_rds_endpoint"></a> [rds\_endpoint](#output\_rds\_endpoint) | RDS instance endpoint |
| <a name="output_ses_configuration_set"></a> [ses\_configuration\_set](#output\_ses\_configuration\_set) | SES configuration set name |
| <a name="output_ses_dkim_tokens"></a> [ses\_dkim\_tokens](#output\_ses\_dkim\_tokens) | DKIM tokens for SES domain |
| <a name="output_ses_domain_identity"></a> [ses\_domain\_identity](#output\_ses\_domain\_identity) | SES domain identity |
| <a name="output_sns_notifications_topic_arn"></a> [sns\_notifications\_topic\_arn](#output\_sns\_notifications\_topic\_arn) | ARN of the SNS notifications topic |
<!-- END_TF_DOCS -->
