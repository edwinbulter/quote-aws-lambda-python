# Reuses the same shared Terraform-state S3 bucket + DynamoDB lock table
# pattern as the quote-lambda-tf reference projects (created once, out of
# band, for all of this AWS account's Terraform-managed projects). Only
# `key` differs per project. This project has a single environment, so
# there is deliberately no `workspace_key_prefix`/workspace branching.

terraform {
  backend "s3" {
    bucket         = "edwinbulter-terraform-state"
    key            = "quote-aws-lambda-python/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
