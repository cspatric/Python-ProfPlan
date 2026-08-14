variable "region" {
  description = "AWS region. us-east-1 unless there is a reason: it is the cheapest and every service exists there."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name, used in every resource name and in the secrets path."
  type        = string
  default     = "production"
}

variable "instance_type" {
  description = <<-EOT
    The application host. t4g is Graviton (ARM): about 20% cheaper than the
    equivalent x86 for the same work, and the images this project builds are
    multi-arch already.

    t4g.small (2 vCPU, 2 GB) is the floor that holds the API, the worker and
    Redis at once. Ollama is NOT on this host: embedding is CPU-bound and would
    starve everything else, which is measured in ADR 0002.
  EOT
  type        = string
  default     = "t4g.small"
}

variable "db_instance_class" {
  description = "db.t4g.micro is the smallest that supports pgvector on Postgres 17."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Gigabytes. Below 20 the price is the same, so 20 is the floor."
  type        = number
  default     = 20
}

variable "domain_name" {
  description = <<-EOT
    Domain the app answers on. Leave empty to skip DNS, the certificate and
    CloudFront: the stack then answers on the instance's public address, which
    is enough to prove it runs and costs nothing extra.
  EOT
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = <<-EOT
    Who may reach SSH. Defaults to nobody on purpose. Opening 22 to 0.0.0.0/0
    is the single most common way a small deployment is taken over; use SSM
    Session Manager, which this instance already has the role for.
  EOT
  type        = list(string)
  default     = []
}

variable "alert_email" {
  description = "Where CloudWatch alarms are sent. Empty means the alarms exist and notify nothing."
  type        = string
  default     = ""
}
