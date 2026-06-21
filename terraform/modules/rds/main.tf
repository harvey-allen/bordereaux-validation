# RDS Module - Managed PostgreSQL database

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "database_name" {
  type = string
}

variable "database_username" {
  type      = string
  sensitive = true
}

variable "database_password" {
  type      = string
  sensitive = true
}

variable "database_allocated_storage" {
  type = number
}

variable "database_engine_version" {
  type = string
}

variable "database_instance_class" {
  type = string
}

variable "database_backup_retention" {
  type = number
}

variable "database_multi_az" {
  type = bool
}

variable "vpc_id" {
  type = string
}

variable "db_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

# RDS Instance
resource "aws_db_instance" "main" {
  identifier            = "${var.project_name}-postgres-${var.environment}"
  db_name              = var.database_name
  username             = var.database_username
  password             = var.database_password
  engine               = "postgres"
  engine_version       = var.database_engine_version
  instance_class       = var.database_instance_class
  allocated_storage    = var.database_allocated_storage
  storage_type         = "gp3"
  storage_encrypted    = true

  # Multi-AZ for high availability
  multi_az = var.database_multi_az

  # Backup configuration
  backup_retention_period = var.database_backup_retention
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"
  copy_tags_to_snapshot  = true

  # Network configuration
  db_subnet_group_name   = aws_db_subnet_group.main.name
  publicly_accessible   = false
  vpc_security_group_ids = [var.security_group_id]

  # Parameter group for PostgreSQL 16
  parameter_group_name = aws_db_parameter_group.main.name

  # Enable enhanced monitoring
  enabled_cloudwatch_logs_exports = ["postgresql"]
  monitoring_interval              = 60
  monitoring_role_arn              = aws_iam_role.rds_monitoring.arn

  # Performance Insights
  performance_insights_enabled          = var.database_instance_class != "db.t4g.micro" ? true : false
  performance_insights_retention_period = 7

  # Skip final snapshot for development, create for production
  skip_final_snapshot       = var.environment == "development" ? true : false
  final_snapshot_identifier = var.environment != "development" ? "${var.project_name}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}" : null

  deletion_protection = var.environment == "production" ? true : false

  tags = {
    Name = "${var.project_name}-postgres-${var.environment}"
  }

  depends_on = [aws_db_subnet_group.main]
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group-${var.environment}"
  subnet_ids = var.db_subnet_ids

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

# Parameter Group
resource "aws_db_parameter_group" "main" {
  family = "postgres16"
  name   = "${var.project_name}-postgres-params-${var.environment}"

  # Enable query logging for debugging
  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_duration"
    value = "1"
  }

  tags = {
    Name = "${var.project_name}-postgres-params"
  }
}

# IAM Role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  name = "${var.project_name}-rds-monitoring-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

output "rds_endpoint" {
  value       = aws_db_instance.main.endpoint
  description = "RDS database endpoint"
  sensitive   = true
}

output "rds_address" {
  value       = aws_db_instance.main.address
  description = "RDS database address"
  sensitive   = true
}

output "rds_port" {
  value       = aws_db_instance.main.port
  description = "RDS database port"
}

output "database_name" {
  value       = aws_db_instance.main.db_name
  description = "RDS database name"
}

output "rds_resource_id" {
  value = aws_db_instance.main.resource_id
}
