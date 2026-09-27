# Infrastructure

Single Terraform folder, single AWS environment (no dev/prod split, no
workspaces). Provisions:

- 3 DynamoDB tables (`quotes`, `user_likes`, `user_progress`)
- A Cognito User Pool + App Client + `USER`/`ADMIN` groups
- A Lambda function (+ `live` alias) running the whole Flask/HTMX app
- An API Gateway HTTP API (`ANY /{proxy+}`) in front of it
- IAM role/policy, CloudWatch log groups

See `../doc/architecture.md` and `../doc/deployment.md` for the full picture.

## First-time setup

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and adjust as needed.
2. Build a real deployment zip first - `aws_lambda_function` needs one to exist
   at apply time:
   ```
   ../scripts/build_lambda_package.sh
   ```
   (A stub `artifacts/placeholder.zip` exists as a fallback if you want to
   stand up the infra skeleton before any app code exists - point
   `lambda_zip_path` at it instead.)
3. `terraform init`
4. `terraform plan`
5. `terraform apply`

## Routine code deploys

After the first apply, don't run `terraform apply` for every code change -
use `../scripts/deploy_code.sh`, which rebuilds the zip and pushes it via
`aws lambda update-function-code` + `publish-version` + `update-alias`,
bypassing Terraform entirely for speed.

## Gotcha

`aws_apigatewayv2_stage.default.default_route_settings` sets
`throttling_burst_limit`/`throttling_rate_limit` explicitly. Do not remove
that block - AWS defaults both to 0 when it's absent, and every request
gets a 429.
