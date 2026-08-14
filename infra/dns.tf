# DNS, the certificate and the CDN.
#
# All of it is skipped when domain_name is empty, which is the default: the
# stack then answers on the instance's address, which is enough to prove it
# runs and costs nothing. Nothing here is required for the application to
# work, and pretending otherwise would make a demo need a domain.

data "aws_route53_zone" "main" {
  count = var.domain_name == "" ? 0 : 1

  name         = var.domain_name
  private_zone = false
}

resource "aws_route53_record" "app" {
  count = var.domain_name == "" ? 0 : 1

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}

# --- the certificate -------------------------------------------------------
# ACM issues it for CloudFront, which must be in us-east-1 whatever region the
# rest of the stack is in. Traefik on the host keeps its own certificate for
# the origin; this one terminates at the edge.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

resource "aws_acm_certificate" "main" {
  count = var.domain_name == "" ? 0 : 1

  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = var.domain_name == "" ? {} : {
    for option in aws_acm_certificate.main[0].domain_validation_options :
    option.domain_name => option
  }

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "main" {
  count = var.domain_name == "" ? 0 : 1

  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for r in aws_route53_record.certificate_validation : r.fqdn]
}

# --- the CDN ---------------------------------------------------------------
# In front of the frontend's static assets. The API is deliberately not cached:
# every response is per user and behind a session cookie, and a CDN in front of
# that is a data leak waiting for a cache key collision.
resource "aws_cloudfront_distribution" "main" {
  count = var.domain_name == "" ? 0 : 1

  enabled = true
  aliases = [var.domain_name]

  origin {
    domain_name = aws_eip.app.public_dns
    origin_id   = "app"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]

    # CachingDisabled. The default behaviour covers the API too, and nothing
    # under /api is cacheable: it is all per user behind a session cookie.
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # AllViewer: the session cookie and the CSRF header have to reach the origin.
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]

    # CachingOptimized. Vite fingerprints these filenames, so they are
    # immutable and safe to cache for a long time.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    acm_certificate_arn = aws_acm_certificate_validation.main[0].certificate_arn
    ssl_support_method  = "sni-only"
  }

  price_class = "PriceClass_100" # North America and Europe; the cheapest tier
}
