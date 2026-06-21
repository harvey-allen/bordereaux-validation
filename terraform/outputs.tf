output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.alb.alb_dns_name
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = module.alb.alb_arn
}

output "backend_ecr_repository_url" {
  description = "ECR repository URL for backend Docker image"
  value       = module.ecr.backend_repository_url
}

output "frontend_ecr_repository_url" {
  description = "ECR repository URL for frontend Docker image"
  value       = module.ecr.frontend_repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.rds_endpoint
  sensitive   = true
}

output "rds_database_name" {
  description = "RDS database name"
  value       = module.rds.database_name
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = module.rds.port
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend assets"
  value       = module.s3_cloudfront.bucket_name
}

output "s3_bucket_regional_domain_name" {
  description = "S3 bucket regional domain name"
  value       = module.s3_cloudfront.bucket_regional_domain_name
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.s3_cloudfront.cloudfront_domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = module.s3_cloudfront.distribution_id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "backend_service_name" {
  description = "ECS backend service name"
  value       = module.ecs.backend_service_name
}

output "frontend_service_name" {
  description = "ECS frontend service name"
  value       = module.ecs.frontend_service_name
}

output "cloudwatch_backend_log_group" {
  description = "CloudWatch log group for backend"
  value       = module.ecs.backend_log_group
}

output "cloudwatch_frontend_log_group" {
  description = "CloudWatch log group for frontend"
  value       = module.ecs.frontend_log_group
}

# CloudWatch Outputs
output "cloudwatch_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms"
  value       = module.cloudwatch.sns_topic_arn
}

output "cloudwatch_alarms" {
  description = "CloudWatch alarm ARNs"
  value       = module.cloudwatch.alarms
}

output "cloudwatch_metrics" {
  description = "CloudWatch custom metrics created"
  value = {
    backend_errors    = module.cloudwatch.backend_error_metric
    backend_warnings  = module.cloudwatch.backend_warning_metric
    database_errors   = module.cloudwatch.database_error_metric
    validation_failures = module.cloudwatch.validation_failure_metric
    frontend_errors   = module.cloudwatch.frontend_error_metric
    frontend_warnings = module.cloudwatch.frontend_warning_metric
  }
}

output "cloudwatch_dashboards" {
  description = "CloudWatch dashboard URLs"
  value       = module.cloudwatch.dashboard_urls
}

output "log_insights_queries" {
  description = "Pre-built CloudWatch Logs Insights queries for monitoring"
  value       = module.cloudwatch.log_insights_queries
  sensitive   = false
}

output "secrets_manager_database_url" {
  description = "Secrets Manager secret name for DATABASE_URL"
  value       = module.secrets.database_url_secret_name
}

output "secrets_manager_api_key" {
  description = "Secrets Manager secret name for API_KEY"
  value       = module.secrets.api_key_secret_name
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = module.vpc.vpc_cidr
}

output "private_subnet_ids" {
  description = "Private subnet IDs for ECS"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs for ALB"
  value       = module.vpc.public_subnet_ids
}

output "environment" {
  description = "Current environment"
  value       = var.environment
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

output "terraform_outputs_path" {
  description = "Path to this outputs file for reference"
  value       = "terraform/outputs.tf"
}
