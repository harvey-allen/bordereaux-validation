# CloudWatch Monitoring Module

## Overview

The dedicated `modules/cloudwatch/` module provides comprehensive monitoring for your Bordereaux application with:

- **Metric Filters** for error tracking, warnings, database issues, and validation failures
- **CloudWatch Alarms** with SNS email notifications
- **Custom Dashboards** for real-time visibility
- **Pre-built Log Insights Queries** for operational insights

## Features

### 1. Metric Filters

The module creates 7 custom metric filters:

**Backend Service:**
- `BackendErrorCount` — Tracks ERROR level logs
- `BackendWarningCount` — Tracks WARNING level logs
- `BackendDatabaseErrorCount` — Detects database errors
- `BackendValidationFailureCount` — Tracks validation failures

**Frontend Service:**
- `FrontendErrorCount` — Tracks frontend errors
- `FrontendWarningCount` — Tracks frontend warnings

All metrics are namespaced as `Bordereaux/{environment}` (e.g., `Bordereaux/production`).

### 2. CloudWatch Alarms

Six automated alarms with SNS email notifications:

| Alarm | Trigger | Threshold | Window |
|-------|---------|-----------|--------|
| Backend Errors | ERROR count exceeds threshold | 10 errors | 5 minutes |
| Backend Warnings | WARNING count exceeds threshold | 50 warnings | 5 minutes |
| Database Errors | Database errors detected | 5 errors | 5 minutes |
| Validation Failures | Validation spike detected | 20 failures | 5 minutes |
| Frontend Errors | Frontend errors detected | 10 errors | 5 minutes |

**Configuration:**
Adjust thresholds in `terraform.tfvars`:
```hcl
error_threshold = 10
warning_threshold = 50
database_error_threshold = 5
```

### 3. CloudWatch Dashboards

Two dashboards created for monitoring:

**Main Overview Dashboard** (`{environment}-bordereaux-overview`)
- 6 key metrics on a single view
- Error trends over time
- Top database errors ranked by frequency

**Backend Detail Dashboard** (`{environment}-bordereaux-backend-detail`)
- Log level summary (INFO, WARNING, ERROR, DEBUG)
- Request duration statistics (average, max, 95th percentile)
- Top 10 error messages by frequency

Access dashboards via Terraform outputs:
```bash
terraform output -json cloudwatch_dashboards
```

### 4. Pre-built Log Insights Queries

The module includes 17 pre-built CloudWatch Logs Insights queries:

**System Health:**
- `errors_last_1h` — Error count in last hour
- `error_rate_trend` — Error rate percentage
- `warnings_and_errors_last_4h` — W/E summary last 4 hours

**Database:**
- `database_slow_queries` — Queries taking >5 seconds
- `database_connection_errors` — Connection failures
- `database_error_breakdown` — Errors by type

**Validation:**
- `validation_failures_by_type` — Failures grouped by error message
- `validation_failure_rate` — Percentage of validations failing

**API Performance:**
- `high_latency_requests` — Requests >10 seconds
- `endpoint_response_times` — Latency stats by endpoint

**Frontend:**
- `frontend_error_summary` — Frontend error count
- `frontend_critical_issues` — Critical/fatal errors

**Operational:**
- `health_check_failures` — Health check failures
- `auth_failures` — Authentication/authorization errors
- `request_rate_by_hour` — Traffic by hour

Access queries:
```bash
terraform output log_insights_queries
```

Use these directly in CloudWatch Logs Insights console:
1. Go to CloudWatch → Logs → Logs Insights
2. Select log group: `{environment}-bordereaux-backend` or `-frontend`
3. Copy query and run

## Configuration

### Required Variables

```hcl
alarm_email = "devops@company.com"  # Email for SNS notifications
```

### Optional Variables

```hcl
log_retention_days = 30              # Default: 30 (overrides ECS setting)
enable_alarms = true                 # Default: true
enable_dashboards = true             # Default: true
error_threshold = 10                 # Default: 10
warning_threshold = 50               # Default: 50
database_error_threshold = 5         # Default: 5
```

## Usage

### 1. Deploy Module

Add `alarm_email` to `terraform.tfvars`:

```hcl
alarm_email = "devops@team.com"
```

Run Terraform:
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. Confirm SNS Subscription

Check email from AWS SNS to confirm subscription to alarm notifications.

### 3. View Dashboards

Get dashboard URLs:
```bash
terraform output cloudwatch_dashboards
```

Or navigate directly:
- AWS Console → CloudWatch → Dashboards → `{environment}-bordereaux-overview`

### 4. Run Log Insights Queries

Query backend logs for errors in the last hour:

```
fields @timestamp, @message, level
| filter level = 'ERROR'
| stats count() as error_count
```

Get pre-built queries:
```bash
terraform output log_insights_queries
```

## Backend Logging Setup

For metric filters to work, application logs must include structured fields:

```python
# Example Python FastAPI logging
import logging
import json

logger = logging.getLogger(__name__)

# Log with level and structured data
logger.error("Validation failed", extra={
    "validation_error": str(e),
    "duration": elapsed_ms
})

logger.warning("Slow database query detected", extra={
    "database": "postgres",
    "duration": 3500
})
```

Log format should parse to:
```
[timestamp] [request_id] [level] [message]
```

**Metric Filter Patterns Used:**

```
# Backend errors
[time, request_id, level = ERROR, ...]

# Backend warnings
[time, request_id, level = WARNING, ...]

# Database errors
[time, request_id, ..., "database", ..., "error"]

# Validation failures
[time, request_id, ..., "validation", ..., "failed"]
```

## Monitoring Best Practices

### 1. Set Appropriate Thresholds

Start with defaults and adjust based on baseline:
- Run for 1 week
- Check average error/warning counts
- Set threshold to 2-3x average to avoid false positives

```bash
# Check error counts in last week
# Use Log Insights: fields @timestamp | stats count() as daily_errors by bin(1d)
```

### 2. React to Alarms

When alarm fires:
1. Check dashboard for trend
2. Query logs with relevant Logs Insights query
3. Check ECS task logs for details: `terraform output cloudwatch_backend_log_group`

```bash
# View recent errors
aws logs tail /{environment}-bordereaux-backend --follow --filter-pattern='ERROR'
```

### 3. Use Dashboards for Trends

Review dashboards:
- Daily: Check error/warning trends
- Weekly: Identify patterns and spike causes
- Monthly: Plan capacity/optimization

### 4. Customize Queries

Create custom queries for your needs:

```
# Query by endpoint
fields @timestamp, @path, @duration
| filter @path like /api\/validate/
| stats count() as requests, pct(@duration, 95) as p95_latency by @path
```

## Troubleshooting

### Alarms Not Firing

1. **Check SNS subscription:** Confirm email subscription to SNS topic
   ```bash
   aws sns list-subscriptions-by-topic --topic-arn $(terraform output -raw cloudwatch_sns_topic_arn)
   ```

2. **Check metric filters:** Verify metrics have data
   ```bash
   aws cloudwatch get-metric-statistics \
     --namespace Bordereaux/production \
     --metric-name BackendErrorCount \
     --start-time 2024-01-01T00:00:00Z \
     --end-time 2024-01-02T00:00:00Z \
     --period 300 \
     --statistics Sum
   ```

3. **Check log format:** Ensure application logs match filter patterns

### Missing Metrics

1. Verify log group names match ECS configuration
2. Check application is writing logs with correct format
3. Inspect first 100 log events:
   ```bash
   aws logs describe-log-streams \
     --log-group-name /{environment}-bordereaux-backend \
     --order-by LastEventTime --descending --max-items 5
   ```

### Dashboard Not Showing Data

- Metrics appear after first error/warning occurs
- Log Insights dashboards query log events directly (no lag)
- Wait 1-2 minutes after application starts for metric data

## Advanced Configuration

### Disable in Development

```hcl
enable_alarms = false
enable_dashboards = false
```

This creates metrics but no alarms or dashboards, reducing costs.

### Increase Log Retention

```hcl
log_retention_days = 90  # Keep logs for 3 months
```

**Cost Impact:** ~$0.50 per GB per month of retention.

### Custom SNS Topic

To use existing SNS topic instead of creating new:

Edit `terraform/modules/cloudwatch/main.tf`:
```hcl
# Change from:
resource "aws_sns_topic" "alarms" { ... }

# To:
data "aws_sns_topic" "alarms" {
  name = "existing-topic-name"
}
```

### Multiple Alarm Recipients

Edit `terraform/modules/cloudwatch/main.tf` to add multiple subscriptions:

```hcl
resource "aws_sns_topic_subscription" "alarm_email_primary" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_sns_topic_subscription" "alarm_email_secondary" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = "secondary@company.com"
}
```

Or use Lambda to send to Slack/Teams instead of email.

## Costs

Estimated monthly costs (production):

| Service | Usage | Cost |
|---------|-------|------|
| CloudWatch Logs Ingestion | 50 GB/month backend + 10 GB/month frontend | ~$30 |
| Custom Metrics | 6 metrics × 30 days | ~$1.80 |
| Alarms | 6 alarms | ~$0.60 |
| Dashboards | 2 dashboards | Free (< 10,000 dashboards API calls) |
| Log Insights | 50 GB scanned/month | ~$2.50 |
| SNS | 100 notifications/month | <$0.01 |
| **Total** | | **~$35** |

To reduce costs:
- Increase `log_retention_days` only for production
- Use fewer alarms in staging
- Disable dashboards in development (`enable_dashboards = false`)

## Next Steps

1. ✅ CloudWatch module deployed with metric filters and alarms
2. ⏭️ **CI/CD Pipeline** — Build Docker images and push to ECR
3. ⏭️ **First Deployment** — Upload frontend to S3, deploy services
4. ⏭️ **Auto-scaling** — Add ECS service auto-scaling configuration
5. ⏭️ **DNS** — Configure Route53 and domain records

See [terraform/README.md](README.md) for deployment steps.
