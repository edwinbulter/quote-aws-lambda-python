output "api_gateway_url" {
  description = "Invoke URL of the deployed API Gateway stage - the app's public URL."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "lambda_function_name" {
  value = aws_lambda_function.quote_app.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.quote_app.arn
}

output "dynamodb_quotes_table_name" {
  value = aws_dynamodb_table.quotes.name
}

output "dynamodb_quotes_table_arn" {
  value = aws_dynamodb_table.quotes.arn
}

output "dynamodb_user_likes_table_name" {
  value = aws_dynamodb_table.user_likes.name
}

output "dynamodb_user_likes_table_arn" {
  value = aws_dynamodb_table.user_likes.arn
}

output "dynamodb_user_progress_table_name" {
  value = aws_dynamodb_table.user_progress.name
}

output "dynamodb_user_progress_table_arn" {
  value = aws_dynamodb_table.user_progress.arn
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "cognito_user_pool_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "custom_domain_url" {
  description = "Public URL of the app on the custom domain."
  value       = "https://${var.custom_domain_name}"
}
