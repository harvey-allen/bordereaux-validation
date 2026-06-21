# SNS Topic for CloudWatch Alarms
resource "aws_sns_topic" "alarms" {
  name              = "${var.environment}-bordereaux-alarms"
  kms_master_key_id = "alias/aws/sns"

  tags = merge(var.tags, {
    Name        = "${var.environment}-bordereaux-alarms"
    Environment = var.environment
  })
}

# SNS Topic Subscription for Email
resource "aws_sns_topic_subscription" "alarm_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ============================================================================
# METRIC FILTERS - Backend
# ============================================================================

# Error metric filter for backend service
resource "aws_cloudwatch_log_group_metric_filter" "backend_errors" {
  name           = "BackendErrors"
  log_group_name = var.backend_log_group_name
  filter_pattern = "[time, request_id, level = ERROR, ...]"

  metric_transformation {
    name      = "BackendErrorCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# Warning metric filter for backend service
resource "aws_cloudwatch_log_group_metric_filter" "backend_warnings" {
  name           = "BackendWarnings"
  log_group_name = var.backend_log_group_name
  filter_pattern = "[time, request_id, level = WARNING, ...]"

  metric_transformation {
    name      = "BackendWarningCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# Database error metric filter
resource "aws_cloudwatch_log_group_metric_filter" "backend_db_errors" {
  name           = "BackendDatabaseErrors"
  log_group_name = var.backend_log_group_name
  filter_pattern = "[time, request_id, ..., \"database\", ..., \"error\"]"

  metric_transformation {
    name      = "BackendDatabaseErrorCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# Validation failure metric filter
resource "aws_cloudwatch_log_group_metric_filter" "backend_validation_failures" {
  name           = "BackendValidationFailures"
  log_group_name = var.backend_log_group_name
  filter_pattern = "[time, request_id, ..., \"validation\", ..., \"failed\"]"

  metric_transformation {
    name      = "BackendValidationFailureCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# ============================================================================
# METRIC FILTERS - Frontend
# ============================================================================

# Frontend error metric filter
resource "aws_cloudwatch_log_group_metric_filter" "frontend_errors" {
  name           = "FrontendErrors"
  log_group_name = var.frontend_log_group_name
  filter_pattern = "[time, id, level = ERROR, ...]"

  metric_transformation {
    name      = "FrontendErrorCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# Frontend warning metric filter
resource "aws_cloudwatch_log_group_metric_filter" "frontend_warnings" {
  name           = "FrontendWarnings"
  log_group_name = var.frontend_log_group_name
  filter_pattern = "[time, id, level = WARNING, ...]"

  metric_transformation {
    name      = "FrontendWarningCount"
    namespace = "Bordereaux/${var.environment}"
    value     = "1"
  }
}

# ============================================================================
# ALARMS
# ============================================================================

# Backend errors alarm
resource "aws_cloudwatch_metric_alarm" "backend_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.environment}-bordereaux-backend-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "BackendErrorCount"
  namespace           = "Bordereaux/${var.environment}"
  period              = "300"
  statistic           = "Sum"
  threshold           = var.error_threshold
  alarm_description   = "Alert when backend errors exceed threshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Name        = "${var.environment}-backend-errors"
    Environment = var.environment
  })
}

# Backend warnings alarm
resource "aws_cloudwatch_metric_alarm" "backend_warnings" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.environment}-bordereaux-backend-warnings"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "BackendWarningCount"
  namespace           = "Bordereaux/${var.environment}"
  period              = "300"
  statistic           = "Sum"
  threshold           = var.warning_threshold
  alarm_description   = "Alert when backend warnings exceed threshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Name        = "${var.environment}-backend-warnings"
    Environment = var.environment
  })
}

# Database errors alarm
resource "aws_cloudwatch_metric_alarm" "backend_db_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.environment}-bordereaux-backend-db-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "BackendDatabaseErrorCount"
  namespace           = "Bordereaux/${var.environment}"
  period              = "300"
  statistic           = "Sum"
  threshold           = var.database_error_threshold
  alarm_description   = "Alert when database errors occur"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Name        = "${var.environment}-backend-db-errors"
    Environment = var.environment
  })
}

# Validation failures alarm
resource "aws_cloudwatch_metric_alarm" "validation_failures" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.environment}-bordereaux-validation-failures"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "2"
  metric_name         = "BackendValidationFailureCount"
  namespace           = "Bordereaux/${var.environment}"
  period              = "300"
  statistic           = "Sum"
  threshold           = 20
  alarm_description   = "Alert when validation failures spike"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Name        = "${var.environment}-validation-failures"
    Environment = var.environment
  })
}

# Frontend errors alarm
resource "aws_cloudwatch_metric_alarm" "frontend_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${var.environment}-bordereaux-frontend-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "FrontendErrorCount"
  namespace           = "Bordereaux/${var.environment}"
  period              = "300"
  statistic           = "Sum"
  threshold           = var.error_threshold
  alarm_description   = "Alert when frontend errors exceed threshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Name        = "${var.environment}-frontend-errors"
    Environment = var.environment
  })
}

# ============================================================================
# DASHBOARDS
# ============================================================================

resource "aws_cloudwatch_dashboard" "main" {
  count          = var.enable_dashboards ? 1 : 0
  dashboard_name = "${var.environment}-bordereaux-overview"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["Bordereaux/${var.environment}", "BackendErrorCount", { stat = "Sum", label = "Backend Errors" }],
            [".", "BackendWarningCount", { stat = "Sum", label = "Backend Warnings" }],
            [".", "BackendDatabaseErrorCount", { stat = "Sum", label = "Database Errors" }],
            [".", "BackendValidationFailureCount", { stat = "Sum", label = "Validation Failures" }],
            [".", "FrontendErrorCount", { stat = "Sum", label = "Frontend Errors" }],
            [".", "FrontendWarningCount", { stat = "Sum", label = "Frontend Warnings" }]
          ]
          period = 300
          stat   = "Sum"
          region = data.aws_region.current.name
          title  = "Bordereaux Application Metrics"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
        x      = 0
        y      = 0
        width  = 24
        height = 6
      },
      {
        type = "log"
        properties = {
          query   = "fields @timestamp, @message | filter @message like /ERROR/ | stats count() by bin(5m)"
          region  = data.aws_region.current.name
          title   = "Backend Error Trend (5-minute bins)"
          queryId = "backend-error-trend"
        }
        x      = 0
        y      = 6
        width  = 12
        height = 6
      },
      {
        type = "log"
        properties = {
          query   = "fields @timestamp, @message | filter @message like /database/ and @message like /error/ | stats count() as error_count by @message | sort error_count desc"
          region  = data.aws_region.current.name
          title   = "Top Database Errors"
          queryId = "top-db-errors"
        }
        x      = 12
        y      = 6
        width  = 12
        height = 6
      }
    ]
  })
}

# Per-service dashboard for detailed backend monitoring
resource "aws_cloudwatch_dashboard" "backend_detail" {
  count          = var.enable_dashboards ? 1 : 0
  dashboard_name = "${var.environment}-bordereaux-backend-detail"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "log"
        properties = {
          query   = "fields @timestamp, @message, level | stats count() as request_count by level"
          region  = data.aws_region.current.name
          title   = "Log Levels Summary"
          queryId = "backend-log-levels"
        }
        x      = 0
        y      = 0
        width  = 12
        height = 6
      },
      {
        type = "log"
        properties = {
          query   = "fields @timestamp, @duration | stats avg(@duration) as avg_ms, max(@duration) as max_ms, pct(@duration, 95) as p95_ms"
          region  = data.aws_region.current.name
          title   = "Request Duration Stats"
          queryId = "backend-duration"
        }
        x      = 12
        y      = 0
        width  = 12
        height = 6
      },
      {
        type = "log"
        properties = {
          query   = "fields @timestamp, @message | filter @message like /ERROR/ | stats count() as error_count by @message | sort error_count desc | limit 10"
          region  = data.aws_region.current.name
          title   = "Top 10 Error Messages"
          queryId = "top-errors"
        }
        x      = 0
        y      = 6
        width  = 24
        height = 6
      }
    ]
  })
}

# Data source for current AWS region
data "aws_region" "current" {}

# ============================================================================
# SAVED LOG INSIGHTS QUERIES
# ============================================================================

# These queries can be manually saved in CloudWatch Logs Insights console
# or imported via AWS API. Documented here for reference.

locals {
  log_insights_queries = {
    # System Health Queries
    "errors_last_1h" = "fields @timestamp, @message, level | filter level = 'ERROR' | stats count() as error_count"

    "error_rate_trend" = "fields @timestamp | stats count() as total_requests | filter level = 'ERROR' | stats count() * 100 / total_requests as error_rate"

    "warnings_and_errors_last_4h" = "fields @timestamp, level | filter level in ['WARNING', 'ERROR'] | stats count() by level"

    # Database Queries
    "database_slow_queries" = "fields @timestamp, @duration, @message | filter @message like /database/ | filter @duration > 5000 | sort @duration desc"

    "database_connection_errors" = "fields @timestamp, @message | filter @message like /connection/ and level = 'ERROR' | stats count() as connection_errors"

    "database_error_breakdown" = "fields @timestamp, @message | filter @message like /database/ and level = 'ERROR' | stats count() by @message"

    # Validation Queries
    "validation_failures_by_type" = "fields @timestamp, @message | filter @message like /validation/ | stats count() as failures by @message"

    "validation_failure_rate" = "fields @timestamp, @message | filter @message like /validation/ and @message like /failed/ | stats count() * 100 / 100 as failure_rate"

    # API Performance Queries
    "high_latency_requests" = "fields @timestamp, @duration, @path, @method | filter @duration > 10000 | sort @duration desc | limit 100"

    "endpoint_response_times" = "fields @timestamp, @path, @duration | stats avg(@duration) as avg_ms, max(@duration) as max_ms, pct(@duration, 95) as p95_ms by @path"

    # Frontend Queries
    "frontend_error_summary" = "fields @timestamp, @message | filter level = 'ERROR' | stats count() as error_count"

    "frontend_critical_issues" = "fields @timestamp, @message | filter level = 'ERROR' and @message like /critical|fatal|crash/ | sort @timestamp desc"

    # Operational Queries
    "health_check_failures" = "fields @timestamp, @message | filter @message like /health/ and @message like /failed/ | stats count() as failures"

    "auth_failures" = "fields @timestamp, @message | filter @message like /auth|authentication|authorization/ and level = 'ERROR' | stats count() as auth_errors"

    "request_rate_by_hour" = "fields @timestamp | stats count() as request_count by bin(1h)"
  }
}

# Output queries as reference for manual setup
output "log_insights_queries" {
  description = "Pre-built CloudWatch Logs Insights queries for common monitoring tasks"
  value       = local.log_insights_queries
}
