variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "eu-central-1"
}

variable "aws_profile" {
  description = "Named AWS CLI profile to use. Leave empty to use the default credential chain."
  type        = string
  default     = ""
}

variable "project_name" {
  description = "Prefix used for naming most resources (Lambda, IAM, API Gateway, Cognito, log groups)."
  type        = string
  default     = "quote-aws-lambda-python"
}

variable "quotes_table_name" {
  type    = string
  default = "quote-aws-lambda-quotes"
}

variable "user_likes_table_name" {
  type    = string
  default = "quote-aws-lambda-user-likes"
}

variable "user_progress_table_name" {
  type    = string
  default = "quote-aws-lambda-user-progress"
}

variable "lambda_memory_size" {
  type    = number
  default = 512
}

variable "lambda_timeout" {
  type    = number
  default = 30
}

variable "lambda_runtime" {
  type    = string
  default = "python3.12"
}

variable "lambda_architecture" {
  type    = string
  default = "arm64"
}

variable "lambda_zip_path" {
  description = "Path to the built Lambda deployment zip, relative to this infrastructure/ folder."
  type        = string
  default     = "../build/lambda.zip"
}

variable "api_throttling_burst_limit" {
  description = "API Gateway stage default throttling burst limit. Must be set explicitly - the AWS default is 0, which 429s every request."
  type        = number
  default     = 100
}

variable "api_throttling_rate_limit" {
  description = "API Gateway stage default throttling rate limit (requests/second). Must be set explicitly - the AWS default is 0, which 429s every request."
  type        = number
  default     = 100
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "seed_users_enabled" {
  description = "Whether the unauthenticated POST /seed-users bootstrap endpoint is enabled."
  type        = bool
  default     = true
}

variable "session_cookie_secure" {
  description = "Whether the id_token/refresh_token cookies get the Secure flag. Set true once served over HTTPS (API Gateway's default domain always is)."
  type        = bool
  default     = true
}
