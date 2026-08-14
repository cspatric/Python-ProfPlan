# Pinned rather than floating. An unpinned provider means the plan you reviewed
# and the plan that applies can be produced by different code, which is exactly
# the property infrastructure as code exists to remove.
terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State holds the database password and every secret this module creates, so
  # it is not a file to leave on a laptop. Uncomment once the bucket exists;
  # it is deliberately not created here, because a module cannot bootstrap the
  # store that holds its own state.
  #
  # backend "s3" {
  #   bucket       = "profplan-tfstate"
  #   key          = "production/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "profplan"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
