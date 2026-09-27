# Deliberately smaller than the quote-lambda-tf-backend reference: no
# Hosted UI domain, no Google/social identity provider, no Identity Pool.
# Flask calls Cognito's Admin* APIs directly (server-side, using the
# Lambda's own execution role), so none of that is needed - see
# doc/auth-flow.md.

resource "aws_cognito_user_pool" "this" {
  name = "${var.project_name}-user-pool"

  alias_attributes         = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_name}-web-client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  id_token_validity      = 1
  access_token_validity  = 1
  refresh_token_validity = 720
  token_validity_units {
    id_token      = "hours"
    access_token  = "hours"
    refresh_token = "hours"
  }

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
}

resource "aws_cognito_user_group" "user_group" {
  name         = "USER"
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 10
}

resource "aws_cognito_user_group" "admin_group" {
  name         = "ADMIN"
  user_pool_id = aws_cognito_user_pool.this.id
  precedence   = 1
}
