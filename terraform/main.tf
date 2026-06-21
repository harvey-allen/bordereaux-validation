# Main Terraform configuration for Bordereaux Validation Infrastructure

module "ecr" {
  source = "./modules/ecr"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
}

module "vpc" {
  source = "./modules/vpc"

  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}

module "secrets" {
  source = "./modules/secrets"

  project_name       = var.project_name
  environment        = var.environment
  dev_api_key        = var.dev_api_key
  admin_emails       = var.admin_emails
  database_password  = var.database_password
}

module "iam" {
  source = "./modules/iam"

  project_name = var.project_name
  environment  = var.environment
}

module "rds" {
  source = "./modules/rds"

  project_name            = var.project_name
  environment             = var.environment
  database_name           = var.database_name
  database_username       = var.database_username
  database_password       = var.database_password
  database_allocated_storage = var.database_allocated_storage
  database_engine_version = var.database_engine_version
  database_instance_class = var.database_instance_class
  database_backup_retention = var.database_backup_retention
  database_multi_az       = var.database_multi_az
  vpc_id                  = module.vpc.vpc_id
  db_subnet_ids           = module.vpc.database_subnet_ids
  security_group_id       = module.vpc.database_security_group_id
}

module "s3_cloudfront" {
  source = "./modules/s3_cloudfront"

  project_name       = var.project_name
  environment        = var.environment
  bucket_name        = var.frontend_bucket_name
  enable_cloudfront  = var.enable_cloudfront
  cloudfront_price_class = var.cloudfront_price_class
}

module "alb" {
  source = "./modules/alb"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  public_subnet_ids      = module.vpc.public_subnet_ids
  certificate_arn        = var.certificate_arn
  alb_security_group_id  = module.vpc.alb_security_group_id
}

module "ecs" {
  source = "./modules/ecs"

  project_name            = var.project_name
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  private_subnet_ids      = module.vpc.private_subnet_ids
  ecs_security_group_id   = module.vpc.ecs_security_group_id
  
  # ECR
  backend_ecr_repository_url = module.ecr.backend_repository_url
  frontend_ecr_repository_url = module.ecr.frontend_repository_url
  backend_image_tag       = var.backend_image_tag
  frontend_image_tag      = var.frontend_image_tag
  
  # Database
  database_host           = module.rds.rds_endpoint
  database_port           = module.rds.port
  database_name           = var.database_name
  database_username       = var.database_username
  
  # Secrets Manager
  database_password_secret_arn = module.secrets.database_password_secret_arn
  api_key_secret_arn      = module.secrets.api_key_secret_arn
  
  # IAM
  ecs_task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  ecs_task_role_arn       = module.iam.ecs_task_role_arn
  
  # ECS Configuration
  desired_count           = var.ecs_desired_count
  backend_task_cpu        = var.backend_task_cpu
  backend_task_memory     = var.backend_task_memory
  frontend_task_cpu       = var.frontend_task_cpu
  frontend_task_memory    = var.frontend_task_memory
  
  # ALB
  backend_target_group_arn = module.alb.backend_target_group_arn
  frontend_target_group_arn = module.alb.frontend_target_group_arn
  
  # Environment
  rds_security_group_id   = module.vpc.database_security_group_id
  cors_allowed_origins    = var.cors_allowed_origins
  admin_emails            = var.admin_emails
  frontend_bucket_name    = var.frontend_bucket_name

  depends_on = [
    module.rds,
    module.alb,
  ]
}

module "cloudwatch" {
  source = "./modules/cloudwatch"

  environment                = var.environment
  backend_log_group_name     = module.ecs.backend_log_group_name
  frontend_log_group_name    = module.ecs.frontend_log_group_name
  alarm_email                = var.alarm_email
  log_retention_days         = var.log_retention_days
  enable_dashboards          = var.enable_dashboards
  enable_alarms              = var.enable_alarms
  error_threshold            = var.error_threshold
  warning_threshold          = var.warning_threshold
  database_error_threshold   = var.database_error_threshold

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  depends_on = [
    module.ecs,
  ]
}
