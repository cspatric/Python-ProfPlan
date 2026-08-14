# CloudWatch.
#
# The stack already has Prometheus, Grafana, Loki and Tempo, and they are
# better at answering questions about the application. What CloudWatch adds is
# the layer underneath: alarms that still fire when the instance those
# containers run on is the thing that is broken.

resource "aws_sns_topic" "alerts" {
  name = "profplan-${var.environment}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_log_group" "containers" {
  name              = "/profplan/${var.environment}/containers"
  retention_in_days = 30 # Loki holds the searchable copy; this is the survivor
}

# The instance is gone or wedged. Everything the app reports goes quiet at the
# same time, which is exactly when an alert from outside the box is the only
# one that can reach anybody.
resource "aws_cloudwatch_metric_alarm" "instance_unhealthy" {
  alarm_name          = "profplan-${var.environment}-instance-unhealthy"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"

  dimensions    = { InstanceId = aws_instance.app.id }
  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# The disk filling up is how this project lost a day already, on the machine it
# was built on. Ollama models and container images grow quietly.
resource "aws_cloudwatch_metric_alarm" "disk_filling" {
  alarm_name          = "profplan-${var.environment}-disk-filling"
  namespace           = "CWAgent"
  metric_name         = "disk_used_percent"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 85
  comparison_operator = "GreaterThanThreshold"

  dimensions    = { InstanceId = aws_instance.app.id, path = "/" }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "database_storage" {
  alarm_name          = "profplan-${var.environment}-db-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 2 * 1024 * 1024 * 1024 # 2 GB
  comparison_operator = "LessThanThreshold"

  dimensions    = { DBInstanceIdentifier = aws_db_instance.main.id }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "database_cpu" {
  alarm_name          = "profplan-${var.environment}-db-cpu-high"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"

  dimensions    = { DBInstanceIdentifier = aws_db_instance.main.id }
  alarm_actions = [aws_sns_topic.alerts.arn]
}
