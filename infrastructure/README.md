# Sumii v2 - OpenTofu Infrastructure

## Overview

This OpenTofu configuration sets up AWS infrastructure for Sumii v2 48-hour MVP:

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

2. **OpenTofu installed** (v1.6+):
   ```bash
   # macOS
   brew install opentofu

   # Linux
   curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o install-opentofu.sh
   chmod +x install-opentofu.sh
   ./install-opentofu.sh --install-method standalone

   # Verify installation
   tofu version
   ```

3. **S3 bucket for OpenTofu state** (create manually first):
   ```bash
   aws s3 mb s3://sumii-tofu-state --region eu-central-1
   aws dynamodb create-table \
     --table-name sumii-tofu-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region eu-central-1
   ```

## 🚀 Usage

### 1. Initialize OpenTofu

```bash
cd /Users/apurva/Work/sumii/sumii-v2/sumii-mobile-api/infrastructure/tofu
tofu init
```

### 2. Review Configuration

```bash
# Check variables
cat variables.tf

# Customize if needed (create terraform.tfvars)
cat > terraform.tfvars <<EOF
environment = "dev"
domain_name = "sumii.de"
aws_region  = "eu-central-1"
EOF
```

### 3. Plan Infrastructure

```bash
tofu plan -out=tfplan
```

Review the plan carefully before applying!

### 4. Apply Infrastructure

```bash
tofu apply tfplan
```

This will create:
- S3 buckets: `sumii-pdfs-dev`, `sumii-documents-dev`
- IAM roles for ECS Fargate
- SES domain identity for `sumii.de`
- SNS/SQS for notifications
- ACM certificate for SSL

### 5. Configure DNS Records

After `tofu apply`, you'll get outputs for DNS configuration:

```bash
tofu output acm_validation_options
tofu output ses_dkim_tokens
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
infrastructure/tofu/
├── main.tf           # Provider and backend configuration
├── variables.tf      # Input variables (NO SECRETS!)
├── s3.tf             # S3 buckets for PDFs and documents
├── iam.tf            # IAM roles and policies
├── ses.tf            # SES email configuration
├── sns_sqs.tf        # SNS topics and SQS queues
├── acm.tf            # SSL/TLS certificates
├── outputs.tf        # Output values
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

## 🔄 AWS Strands Agents Integration

For deploying Strands Agents to AWS Fargate, see:
- https://strandsagents.com/latest/documentation/docs/user-guide/deploy/deploy_to_aws_fargate/

Key components:
- ECS Fargate cluster (create after MVP infrastructure)
- Task definitions with Strands runtime
- Service with load balancer
- Auto-scaling policies

## 💰 Cost Estimation (48-hour MVP)

```
S3 storage:           ~$0.023/GB/month
SES emails:           $0.10 per 1,000 emails
SNS push:             $0.50 per 1M requests
SQS:                  $0.40 per 1M requests
ACM certificates:     FREE
Data transfer:        $0.09/GB (out to internet)

Estimated MVP cost:   ~$5-10 for 48 hours
```

## 🧹 Cleanup

To destroy all resources:

```bash
# WARNING: This deletes EVERYTHING
tofu destroy

# Confirm by typing 'yes'
```

## 📝 Notes

- **Default VPC**: For 48-hour MVP, use AWS default VPC (no custom VPC needed)
- **ECS Fargate**: Configure separately after MVP infrastructure is ready
- **RDS**: Use local PostgreSQL for MVP, add RDS in production
- **Monitoring**: Add CloudWatch alarms after MVP is functional

## 🆘 Troubleshooting

### Issue: State lock error
```bash
# Release lock (if tofu crashed)
tofu force-unlock LOCK_ID
```

### Issue: Certificate validation stuck
```
# Check DNS records are correct
dig _xxxxx.sumii.de CNAME

# Wait up to 45 minutes for validation
```

### Issue: SES in sandbox mode
```bash
# Request production access
aws ses put-account-sending-enabled --enabled --region eu-central-1

# Or test with verified email addresses only
```

## 📚 Resources

- [OpenTofu Docs](https://opentofu.org/docs/)
- [OpenTofu AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS Strands Agents Deployment](https://strandsagents.com/latest/documentation/docs/user-guide/deploy/deploy_to_aws_fargate/)
- [AWS ECS Fargate Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/intro.html)

## 🔄 Why OpenTofu?

OpenTofu is an open-source, community-driven Terraform fork that:
- ✅ Fully compatible with Terraform configurations
- ✅ Uses same HCL syntax
- ✅ Open governance model (Linux Foundation)
- ✅ No vendor lock-in
- ✅ Actively maintained by community

**Migration from Terraform**: Simply replace `terraform` commands with `tofu` commands!

```bash
# Terraform → OpenTofu
terraform init   →  tofu init
terraform plan   →  tofu plan
terraform apply  →  tofu apply
terraform destroy → tofu destroy
```
