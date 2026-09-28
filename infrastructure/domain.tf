# Custom domain for the API, using an existing Route 53 public hosted
# zone (kabulter.click) that lives outside this project's Terraform.
#
# ACM cert must be issued in this project's own region (eu-central-1),
# NOT us-east-1 - that requirement only applies to CloudFront/edge-
# optimized API Gateway custom domains, not the REGIONAL endpoint_type
# used below.

data "aws_route53_zone" "this" {
  name         = var.route53_zone_name
  private_zone = false
}

resource "aws_acm_certificate" "custom_domain" {
  domain_name       = var.custom_domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.custom_domain.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = data.aws_route53_zone.this.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true # protects re-applies (e.g. after a cert replacement) from a transient same-name record
}

resource "aws_acm_certificate_validation" "custom_domain" {
  certificate_arn         = aws_acm_certificate.custom_domain.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

resource "aws_apigatewayv2_domain_name" "custom_domain" {
  domain_name = var.custom_domain_name

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.custom_domain.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

# No api_mapping_key -> maps at the domain root, so routes stay at
# https://quote-aws-lambda-python.kabulter.click/... with no path prefix.
resource "aws_apigatewayv2_api_mapping" "custom_domain" {
  api_id      = aws_apigatewayv2_api.http_api.id
  domain_name = aws_apigatewayv2_domain_name.custom_domain.id
  stage       = aws_apigatewayv2_stage.default.id
}

resource "aws_route53_record" "custom_domain" {
  zone_id = data.aws_route53_zone.this.zone_id
  name    = var.custom_domain_name
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.custom_domain.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.custom_domain.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
