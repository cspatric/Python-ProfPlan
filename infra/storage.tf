# S3, in place of MinIO.
#
# The application speaks the S3 API already, so this is a configuration change
# rather than a code change: MinIO exists locally precisely so that this line
# is the only difference.

resource "aws_s3_bucket" "documents" {
  bucket = "profplan-${var.environment}-documents"

  # An uploaded document is the thing a teacher cannot re-create. Deleting the
  # bucket has to be an act, not a consequence of a plan.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  # An overwrite or a delete is recoverable. The ingestion writes each object
  # once under a uuid, so versions accumulate slowly; the rule below keeps
  # that from becoming a bill.
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
