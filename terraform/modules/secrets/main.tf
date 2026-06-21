# Secrets Manager Module - Store sensitive values

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "dev_api_key" {
  type      = string
  sensitive = true
}

variable "admin_emails" {
  type = string
}

variable "database_password" {
  type      = string
  sensitive = true
}

resource "aws_secretsmanager_secret" "database_password" {
  name = "${var.project_name}/${var.environment}/database-password"
  
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-database-password"
  }
}

resource "aws_secretsmanager_secret_version" "database_password" {
  secret_id     = aws_secretsmanager_secret.database_password.id
  secret_string = var.database_password
}

resource "aws_secretsmanager_secret" "api_key" {
  name = "${var.project_name}/${var.environment}/api-key"

  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-api-key"
  }
}

resource "aws_secretsmanager_secret_version" "api_key" {
  secret_id     = aws_secretsmanager_secret.api_key.id
  secret_string = var.dev_api_key
}

resource "aws_secretsmanager_secret" "admin_emails" {
  name = "${var.project_name}/${var.environment}/admin-emails"

  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-admin-emails"
  }
}

resource "aws_secretsmanager_secret_version" "admin_emails" {
  secret_id     = aws_secretsmanager_secret.admin_emails.id
  secret_string = var.admin_emails
}

output "database_password_secret_arn" {
  value = aws_secretsmanager_secret.database_password.arn
}

output "database_password_secret_name" {
  value = aws_secretsmanager_secret.database_password.name
}

output "api_key_secret_arn" {
  value = aws_secretsmanager_secret.api_key.arn
}

output "api_key_secret_name" {
  value = aws_secretsmanager_secret.api_key.name
}

output "admin_emails_secret_arn" {
  value = aws_secretsmanager_secret.admin_emails.arn
}

output "admin_emails_secret_name" {
  value = aws_secretsmanager_secret.admin_emails.name
}
