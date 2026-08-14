# PostgreSQL with pgvector.
#
# RDS rather than Postgres in a container on the host, for one reason that
# matters more than the price difference: docs/deployment/BACKUP.md says the
# recovery point today is "the last time a human remembered". RDS takes daily
# snapshots and keeps write-ahead logs, which turns that into a number.

resource "random_password" "database" {
  length  = 48
  special = false # RDS rejects several punctuation characters in a password
}

resource "aws_db_parameter_group" "main" {
  name   = "profplan-${var.environment}-pg17"
  family = "postgres17"

  # pgvector has to be loadable before the extension can be created. Without
  # this the first migration fails on CREATE EXTENSION vector.
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  # Every statement over a second, in the log. The cheapest slow query log
  # there is, and the first thing anyone asks for during an incident.
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

resource "aws_db_instance" "main" {
  identifier     = "profplan-${var.environment}"
  engine         = "postgres"
  engine_version = "17.5"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5 # grows on its own before it fills
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "profplan"
  username = "profplan"
  password = random_password.database.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.main.name

  # Backups. This is the whole reason for RDS over a container.
  backup_retention_period = 7
  backup_window           = "03:00-04:00" # UTC, before the school day anywhere
  copy_tags_to_snapshot   = true

  maintenance_window         = "sun:04:00-sun:05:00"
  auto_minor_version_upgrade = true

  # Single AZ: a deliberate trade, and the reason the SLO says 99% and not
  # 99.9%. Multi-AZ doubles the bill to remove a failure mode this project has
  # not yet been hurt by. Flip it when the objective changes, not before.
  multi_az = false

  performance_insights_enabled    = true
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # A final snapshot on destroy, and no accidental destroys. Terraform will
  # refuse to delete this until someone means it.
  skip_final_snapshot       = false
  final_snapshot_identifier = "profplan-${var.environment}-final"
  deletion_protection       = true

  lifecycle {
    # The generated password lives in state; rotating it is done in SSM and
    # the console, not by a plan that would recreate the instance.
    ignore_changes = [password]
  }
}
