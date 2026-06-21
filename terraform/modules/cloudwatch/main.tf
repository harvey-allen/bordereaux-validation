# CloudWatch Log Groups for Backend
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/${var.project_name}-${var.environment}-backend"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-backend"
    Environment = var.environment
  })
}

# CloudWatch Log Groups for Frontend
resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/${var.project_name}-${var.environment}-frontend"
  retention_in_days = var.log_retention_days

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-frontend"
    Environment = var.environment
  })
}
