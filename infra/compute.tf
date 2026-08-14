# The application host.
#
# One instance running the same compose stack that runs locally. That is the
# point of the modular monolith in ADR 0001: production is not a different
# architecture, it is the same containers with the database and the object
# store pointed elsewhere.

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-kernel-6.1-arm64"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region       = var.region
    secrets_path = local.secrets_path
    bucket       = aws_s3_bucket.documents.bucket
    environment  = var.environment
  })
  # Changing the bootstrap replaces the instance rather than leaving a host
  # running code nobody can reproduce.
  user_data_replace_on_change = true

  root_block_device {
    volume_size = 40 # the images and the Ollama models are the bulk of it
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only: the fix for the SSRF-to-credentials path
  }

  monitoring = true

  tags = { Name = "profplan-${var.environment}" }
}

# A fixed address, so DNS does not have to be edited every time the instance
# is replaced.
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = { Name = "profplan-${var.environment}" }
}
