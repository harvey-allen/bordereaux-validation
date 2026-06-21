variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "bordereaux"
}

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for multi-AZ deployment"
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b"]
}

# Database Configuration
variable "database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "bordereaux"
}

variable "database_username" {
  description = "PostgreSQL admin username"
  type        = string
  default     = "postgres"
  sensitive   = true
}

variable "database_password" {
  description = "PostgreSQL admin password (min 16 chars, must contain uppercase, lowercase, number, special char)"
  type        = string
  sensitive   = true
}

variable "database_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 20
}

variable "database_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "16.1"
}

variable "database_instance_class" {
  description = "RDS instance class (db.t4g.micro, db.t4g.small, db.t4g.medium, etc.)"
  type        = string
  default     = "db.t4g.micro"
}

variable "database_backup_retention" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

variable "database_multi_az" {
  description = "Enable multi-AZ deployment for high availability"
  type        = bool
  default     = false
}

# ECS Configuration
variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "backend_task_cpu" {
  description = "CPU units for backend task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "backend_task_memory" {
  description = "Memory in MB for backend task (512-30720, must be valid for CPU)"
  type        = number
  default     = 1024
}

variable "frontend_task_cpu" {
  description = "CPU units for frontend task"
  type        = number
  default     = 256
}

variable "frontend_task_memory" {
  description = "Memory in MB for frontend task"
  type        = number
  default     = 512
}

# API Keys and Secrets
variable "dev_api_key" {
  description = "Development/default API key for testing"
  type        = string
  sensitive   = true
}

variable "admin_emails" {
  description = "Comma-separated list of admin email addresses"
  type        = string
}

variable "cors_allowed_origins" {
  description = "Comma-separated list of CORS-allowed origins for production"
  type        = string
}

# S3 and CloudFront
variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend assets (must be globally unique)"
  type        = string
}

variable "enable_cloudfront" {
  description = "Enable CloudFront CDN for frontend"
  type        = bool
  default     = true
}

variable "cloudfront_price_class" {
  description = "CloudFront price class (PriceClass_100, PriceClass_200, PriceClass_All)"
  type        = string
  default     = "PriceClass_100"
}

# Auto-scaling
variable "enable_autoscaling" {
  description = "Enable auto-scaling for ECS services"
  type        = bool
  default     = true
}

variable "autoscaling_min_capacity" {
  description = "Minimum number of tasks for auto-scaling"
  type        = number
  default     = 1
}

variable "autoscaling_max_capacity" {
  description = "Maximum number of tasks for auto-scaling"
  type        = number
  default     = 3
}

variable "autoscaling_target_cpu" {
  description = "Target CPU percentage for auto-scaling"
  type        = number
  default     = 70
}

# ACM Certificate
variable "certificate_arn" {
  description = "ARN of SSL/TLS certificate in ACM (leave empty to create self-signed)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "domain_name" {
  description = "Domain name for the application (optional, for certificate validation)"
  type        = string
  default     = ""
}

# Docker Images
variable "backend_image_tag" {
  description = "Backend Docker image tag"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Frontend Docker image tag"
  type        = string
  default     = "latest"
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs (staging/production)"
  type        = number
  default     = 7
}
