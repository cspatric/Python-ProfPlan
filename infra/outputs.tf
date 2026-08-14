output "app_public_ip" {
  description = "Where the stack answers. Point DNS here, or use it directly."
  value       = aws_eip.app.public_ip
}

output "database_endpoint" {
  description = "Host and port. The full URL, with the password, is in SSM."
  value       = aws_db_instance.main.endpoint
}

output "documents_bucket" {
  description = "S3 bucket the uploads go to, in place of MinIO."
  value       = aws_s3_bucket.documents.bucket
}

output "secrets_path" {
  description = "Where the app reads its secrets from. SECRETS_PATH on the host."
  value       = local.secrets_path
}

output "connect_command" {
  description = "Reach the host without opening SSH."
  value       = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.region}"
}

output "set_api_keys" {
  description = "The keys Terraform creates empty and a human fills in."
  value = join("\n", [
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"] :
    "aws ssm put-parameter --name ${local.secrets_path}/${key} --type SecureString --value '...' --overwrite"
  ])
}
