# Terraform Infrastructure as Code - Bordereaux Validation

Complete infrastructure setup for production deployment on AWS ECS Fargate with managed PostgreSQL, S3, and CloudFront CDN.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          CloudFront CDN                         │
│                    (Frontend Asset Distribution)                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Application Load Balancer                    │
│              (HTTPS Listener + Health Checks)                   │
└───────────────┬─────────────────────────────────┬───────────────┘
                │                                 │
        ┌───────▼────────┐            ┌───────────▼──────┐
        │  Backend Srv   │            │ Frontend Service │
        │  ECS Fargate   │            │   ECS Fargate    │
        │  (Task CPU:512 │            │ (Task CPU: 256)  │
        │  Memory: 1GB)  │            │ (Memory: 512MB)  │
        └───────┬────────┘            └───────────┬──────┘
                │                                 │
                ├─────────────────┬───────────────┤
                │                 │               │
        ┌───────▼────────┐    ┌───▼──────┐   ┌──▼──────────┐
        │ RDS PostgreSQL │    │ S3 Bucket│   │ ECR Repos   │
        │ (Multi-AZ)     │    │ (Static  │   │ (Backend &  │
        │ (Automated     │    │  Assets) │   │  Frontend)  │
        │  Backups)      │    └──────────┘   └─────────────┘
        └────────────────┘
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** >= 1.0 installed
3. **AWS CLI** configured with credentials
4. **Docker** for building images
5. **Git** for version control

## Quick Start

### 1. Initialize Terraform

```bash
cd terraform
terraform init
```

### 2. Copy and Configure Variables

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your configuration
```

### 3. Validate Configuration

```bash
terraform validate
terraform plan
```

### 4. Deploy Infrastructure

```bash
terraform apply
```

## Configuration Variables

### Environment

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `environment` | Yes | — | deployment environment: `development`, `staging`, or `production` |
| `aws_region` | No | `eu-west-2` | AWS region for all resources |

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `database_password` | Yes | — | PostgreSQL admin password (min 16 chars, must include uppercase, lowercase, number, special char) |
| `database_instance_class` | No | `db.t4g.micro` | RDS instance type (use `db.t4g.small` for production) |
| `database_allocated_storage` | No | `20` | Storage in GB |
| `database_multi_az` | No | `false` | Enable high availability |
| `database_backup_retention` | No | `7` | Backup retention days |

### ECS Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ecs_desired_count` | No | `1` | Number of tasks to run (increase for HA) |
| `backend_task_cpu` | No | `512` | CPU units (256, 512, 1024, 2048, 4096) |
| `backend_task_memory` | No | `1024` | Memory in MB |
| `frontend_task_cpu` | No | `256` | CPU units |
| `frontend_task_memory` | No | `512` | Memory in MB |

### API Keys & Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `dev_api_key` | Yes | — | API key for authentication |
| `admin_emails` | Yes | — | Comma-separated admin emails |
| `cors_allowed_origins` | Yes | — | Comma-separated CORS-allowed domains |

### Frontend & CDN

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `frontend_bucket_name` | Yes | — | S3 bucket name (must be globally unique) |
| `enable_cloudfront` | No | `true` | Enable CloudFront CDN |
| `cloudfront_price_class` | No | `PriceClass_100` | CloudFront pricing tier |
| `certificate_arn` | No | — | ACM certificate ARN (auto-generated if empty) |

### Docker Images

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `backend_image_tag` | No | `latest` | ECR image tag for backend |
| `frontend_image_tag` | No | `latest` | ECR image tag for frontend |

## Deployment Scenarios

### Staging Deployment

```bash
# Create terraform.tfvars
cat > terraform/terraform.tfvars << EOF
environment = "staging"
database_instance_class = "db.t4g.micro"
database_allocated_storage = 20
ecs_desired_count = 1
backend_task_cpu = 512
backend_task_memory = 1024
frontend_bucket_name = "bordereaux-frontend-staging"
dev_api_key = "your-staging-key"
admin_emails = "admin@staging.com"
cors_allowed_origins = "https://staging.your-domain.com"
EOF

# Deploy
terraform apply
```

### Production Deployment

```bash
cat > terraform/terraform.tfvars << EOF
environment = "production"
database_instance_class = "db.t4g.small"
database_multi_az = true
database_allocated_storage = 100
ecs_desired_count = 2
backend_task_cpu = 1024
backend_task_memory = 2048
enable_autoscaling = true
autoscaling_min_capacity = 2
autoscaling_max_capacity = 5
frontend_bucket_name = "bordereaux-frontend-prod"
dev_api_key = "your-production-key"
admin_emails = "admin@company.com,devops@company.com"
cors_allowed_origins = "https://your-domain.com"
certificate_arn = "arn:aws:acm:eu-west-2:xxx:certificate/xxx"
EOF

# Deploy
terraform apply
```

## Outputs

After deployment, Terraform outputs important values:

```bash
# View outputs
terraform output

# Get specific output
terraform output alb_dns_name
terraform output rds_endpoint
terraform output cloudfront_domain_name
```

Key outputs:

| Output | Use |
|--------|-----|
| `alb_dns_name` | Add CNAME record to your domain |
| `cloudfront_domain_name` | Frontend CDN endpoint |
| `backend_ecr_repository_url` | Push backend Docker image |
| `frontend_ecr_repository_url` | Push frontend Docker image |
| `rds_endpoint` | Update DATABASE_URL in application |
| `ecs_cluster_name` | Reference for ECS updates |

## Post-Deployment Steps

### 1. Build and Push Docker Images

```bash
# Backend
docker build -t bordereaux-backend:latest ./backend
docker tag bordereaux-backend:latest <BACKEND_ECR_REPO>:latest
docker push <BACKEND_ECR_REPO>:latest

# Frontend
docker build -t bordereaux-frontend:latest ./frontend
docker tag bordereaux-frontend:latest <FRONTEND_ECR_REPO>:latest
docker push <FRONTEND_ECR_REPO>:latest
```

Replace `<BACKEND_ECR_REPO>` and `<FRONTEND_ECR_REPO>` with values from `terraform output`.

### 2. Update ECS Services

```bash
# Force new deployment
aws ecs update-service \
  --cluster bordereaux-cluster-staging \
  --service bordereaux-backend-service-staging \
  --force-new-deployment
```

### 3. Upload Frontend Assets to S3

```bash
# Build frontend
npm run build --prefix frontend

# Upload to S3
aws s3 sync frontend/build/ \
  s3://bordereaux-frontend-staging/ \
  --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*"
```

### 4. Configure DNS

Add CNAME record to your DNS:

```
api.your-domain.com  CNAME  bordereaux-alb-staging-xxx.eu-west-2.elb.amazonaws.com
cdn.your-domain.com  CNAME  dxxx.cloudfront.net
```

## Remote State Management (Recommended for Teams)

Store Terraform state in S3 with DynamoDB locking:

```bash
# Create state bucket
aws s3 mb s3://bordereaux-terraform-state --region eu-west-2

# Create DynamoDB table for locks
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
  --region eu-west-2

# Uncomment backend block in providers.tf
# terraform init
```

## Monitoring & Logging

### CloudWatch Logs

Access logs via AWS Console or CLI:

```bash
# Backend logs
aws logs tail /ecs/bordereaux-backend-staging --follow

# Frontend logs
aws logs tail /ecs/bordereaux-frontend-staging --follow
```

### RDS Monitoring

Performance Insights enabled for instances >= t4g.small:

```bash
# View in AWS Console: RDS → Databases → Performance Insights
```

### ALB Metrics

View in AWS Console: EC2 → Load Balancers → Select ALB → Monitoring

## Updating Infrastructure

### Scale Up Services

```bash
# Update task count
terraform apply -var="ecs_desired_count=3"

# Update task size
terraform apply -var="backend_task_cpu=1024" -var="backend_task_memory=2048"
```

### Update Database

```bash
# Increase storage (non-blocking)
terraform apply -var="database_allocated_storage=100"

# Change instance class (downtime required)
terraform apply -var="database_instance_class=db.t4g.small"
```

### Update Frontend Assets

```bash
# Rebuild and upload
npm run build --prefix frontend
aws s3 sync frontend/build/ s3://bordereaux-frontend-staging/ --delete
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

## Cost Optimization

- **Use Fargate Spot**: Lower cost with interruption tolerance
  ```bash
  terraform apply -var="capacity_provider=FARGATE_SPOT"
  ```
- **Enable autoscaling**: Scale down during off-hours
- **Use CloudFront**: Reduces ALB load and improves user experience
- **Database**: Use `db.t4g.micro` for development/staging

## Troubleshooting

### ECS Tasks Not Starting

```bash
# Check task logs
aws ecs describe-tasks \
  --cluster bordereaux-cluster-staging \
  --tasks <TASK_ARN>

# Check CloudWatch logs
aws logs describe-log-streams \
  --log-group-name /ecs/bordereaux-backend-staging
```

### ALB Health Checks Failing

```bash
# SSH into task and test backend health
curl http://localhost:8000/health
```

### RDS Connection Timeout

- Verify security group allows traffic from ECS security group
- Check database is running and endpoint is accessible
- Verify DATABASE_URL format in task definition

### CloudFront Cache Issues

```bash
# Invalidate entire cache
aws cloudfront create-invalidation \
  --distribution-id <ID> \
  --paths "/*"
```

## Cleanup

**Danger: This destroys all infrastructure!**

```bash
terraform destroy
```

Confirm and wait for cleanup to complete.

## Support & Documentation

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-best-practices.html)
- [AWS RDS PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
