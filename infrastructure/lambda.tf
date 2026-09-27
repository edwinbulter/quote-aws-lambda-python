# `aws_lambda_function` needs a real zip to exist at apply time. Run
# scripts/build_lambda_package.sh (or scripts/deploy_infra.sh, which does
# it for you) before the first `terraform apply`. Every apply after that
# picks up source_code_hash changes automatically; routine code-only
# deploys instead use scripts/deploy_code.sh, which bypasses Terraform
# entirely (update-function-code + publish-version + update-alias), so
# `terraform apply` stays fast and rare.

resource "aws_lambda_function" "quote_app" {
  function_name = var.project_name
  role          = aws_iam_role.lambda_exec.arn

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  handler       = "app.lambda_handler.handler"
  runtime       = var.lambda_runtime
  architectures = [var.lambda_architecture]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  publish = true

  environment {
    variables = {
      QUOTES_TABLE          = aws_dynamodb_table.quotes.name
      USER_LIKES_TABLE      = aws_dynamodb_table.user_likes.name
      USER_PROGRESS_TABLE   = aws_dynamodb_table.user_progress.name
      COGNITO_USER_POOL_ID  = aws_cognito_user_pool.this.id
      COGNITO_APP_CLIENT_ID = aws_cognito_user_pool_client.web.id
      SEED_USERS_ENABLED    = tostring(var.seed_users_enabled)
      SESSION_COOKIE_SECURE = tostring(var.session_cookie_secure)
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_policy_attach]
}

# Note: app/aws_clients.py reads the AWS_REGION env var, which the Lambda
# runtime always sets automatically to the function's own region (it's a
# reserved key Terraform/app code must not set explicitly) - so no region
# variable is passed above.

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.quote_app.function_name
  function_version = aws_lambda_function.quote_app.version
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_alias.live.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
