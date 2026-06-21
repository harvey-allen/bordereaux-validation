variable "environment" {
  description = "Environment name (development, staging, production)"
  type        = string

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be development, staging, or production."
  }
}

variable "backend_log_group_name" {
  description = "CloudWatch log group name for backend service"
  type        = string
}

variable "frontend_log_group_name" {
  description = "CloudWatch log group name for frontend service"
  type        = string
}

variable "alarm_email" {
  description = "Email address to receive alarm notifications"
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain logs (overrides ECS setting)"
  type        = number
  default     = 30
}

variable "enable_dashboards" {
  description = "Whether to create CloudWatch dashboards"
  type        = bool
  default     = true
}

variable "enable_alarms" {
  description = "Whether to create CloudWatch alarms"
  type        = bool
  default     = true
}

variable "error_threshold" {
  description = "Number of errors in 5 minutes to trigger alarm"
  type        = number
  default     = 10
}

variable "warning_threshold" {
  description = "Number of warnings in 5 minutes to trigger alarm"
  type        = number
  default     = 50
}

variable "database_error_threshold" {
  description = "Number of database errors in 5 minutes to trigger alarm"
  type        = number
  default     = 5
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
