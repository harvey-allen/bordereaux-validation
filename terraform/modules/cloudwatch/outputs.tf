output "sns_topic_arn" {
  description = "ARN of SNS topic for CloudWatch alarms"
  value       = aws_sns_topic.alarms.arn
}

output "sns_topic_name" {
  description = "Name of SNS topic for CloudWatch alarms"
  value       = aws_sns_topic.alarms.name
}

output "backend_error_metric" {
  description = "Backend error metric name"
  value       = aws_cloudwatch_log_group_metric_filter.backend_errors.metric_transformation[0].name
}

output "backend_warning_metric" {
  description = "Backend warning metric name"
  value       = aws_cloudwatch_log_group_metric_filter.backend_warnings.metric_transformation[0].name
}

output "database_error_metric" {
  description = "Database error metric name"
  value       = aws_cloudwatch_log_group_metric_filter.backend_db_errors.metric_transformation[0].name
}

output "validation_failure_metric" {
  description = "Validation failure metric name"
  value       = aws_cloudwatch_log_group_metric_filter.backend_validation_failures.metric_transformation[0].name
}

output "frontend_error_metric" {
  description = "Frontend error metric name"
  value       = aws_cloudwatch_log_group_metric_filter.frontend_errors.metric_transformation[0].name
}

output "frontend_warning_metric" {
  description = "Frontend warning metric name"
  value       = aws_cloudwatch_log_group_metric_filter.frontend_warnings.metric_transformation[0].name
}

output "alarms" {
  description = "CloudWatch alarm names and ARNs"
  value = var.enable_alarms ? {
    backend_errors            = try(aws_cloudwatch_metric_alarm.backend_errors[0].arn, null)
    backend_warnings          = try(aws_cloudwatch_metric_alarm.backend_warnings[0].arn, null)
    database_errors           = try(aws_cloudwatch_metric_alarm.backend_db_errors[0].arn, null)
    validation_failures       = try(aws_cloudwatch_metric_alarm.validation_failures[0].arn, null)
    frontend_errors           = try(aws_cloudwatch_metric_alarm.frontend_errors[0].arn, null)
  } : {}
}

output "dashboard_urls" {
  description = "URLs to CloudWatch dashboards"
  value = var.enable_dashboards ? {
    main_overview = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.main[0].dashboard_name}"
    backend_detail = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.backend_detail[0].dashboard_name}"
  } : {}
}

output "log_insights_queries" {
  description = "Pre-built CloudWatch Logs Insights queries"
  value       = local.log_insights_queries
}
