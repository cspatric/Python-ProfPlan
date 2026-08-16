# The secrets the application reads at boot.
#
# SSM Parameter Store, for the reasoning in docs/deployment/SECRETS.md: these
# are a handful of strings that rotate rarely, SecureString encrypts them with
# KMS just the same, and Parameter Store is free at this size while Secrets
# Manager bills per secret per month.
#
# The parameter name after the prefix IS the environment variable, which is
# what lets a new secret be added without touching the application.

locals {
  secrets_path = "/profplan/${var.environment}"

  # Generated here because nothing else needs to know them. The API keys are
  # not in this list on purpose: they come from outside and are written by
  # hand, see the note at the bottom of this file.
  generated_secrets = {
    SECRET_KEY          = random_password.app_secret.result
    JWT_ACCESS_SECRET   = random_password.jwt_access.result
    JWT_REFRESH_SECRET  = random_password.jwt_refresh.result
    POSTGRES_PASSWORD   = random_password.database.result
    MINIO_ROOT_PASSWORD = random_password.storage.result
  }
}

resource "random_password" "app_secret" {
  length  = 48
  special = false
}

resource "random_password" "jwt_access" {
  length  = 48
  special = false
}

resource "random_password" "jwt_refresh" {
  length  = 48
  special = false
}

# Kept even on S3: the application still reads the variable, and leaving it
# empty would trip the startup audit that refuses placeholder secrets.
resource "random_password" "storage" {
  length  = 48
  special = false
}

resource "aws_ssm_parameter" "generated" {
  for_each = local.generated_secrets

  name  = "${local.secrets_path}/${each.key}"
  type  = "SecureString"
  value = each.value

  tags = { Name = each.key }
}

# The database URL, assembled from the instance so nobody has to paste a host.
resource "aws_ssm_parameter" "database_url" {
  name = "${local.secrets_path}/DATABASE_URL"
  type = "SecureString"
  value = format(
    "postgresql+asyncpg://%s:%s@%s/%s",
    aws_db_instance.main.username,
    random_password.database.result,
    aws_db_instance.main.endpoint,
    aws_db_instance.main.db_name,
  )
}

# --- the ones that come from outside --------------------------------------
# Created empty and never read back. Terraform owns the existence of the
# parameter; a human owns the value, written once with:
#
#   aws ssm put-parameter --name /profplan/production/OPENAI_API_KEY \
#     --type SecureString --value "sk-..." --overwrite
#
# ignore_changes is what makes that safe. Without it the next apply would
# helpfully put the placeholder back and take the AI offline.
resource "aws_ssm_parameter" "external" {
  for_each = toset([
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "SMTP_PASSWORD",
    "BEDROCK_API_KEY",
  ])

  name  = "${local.secrets_path}/${each.value}"
  type  = "SecureString"
  value = "set-me-with-the-cli"

  lifecycle {
    ignore_changes = [value]
  }
}
