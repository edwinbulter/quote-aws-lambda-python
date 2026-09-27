# Deployment

## First-time setup

```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars   # edit as needed
../scripts/build_lambda_package.sh              # aws_lambda_function needs a real zip to exist at apply time
terraform init
terraform plan
terraform apply
```

(Or just run `scripts/deploy_infra.sh`, which does the build + init/plan/apply
for you with a confirmation prompt.)

After `apply`, bootstrap demo accounts and check everything works:

```bash
API_URL=$(terraform -chdir=infrastructure output -raw api_gateway_url)
curl -X POST "$API_URL/seed-users"     # creates admin/Admin123! (ADMIN) and user-1/Hello-user-1 (USER)
../scripts/smoke_test.sh "$API_URL"
```

## Routine code changes

Don't run `terraform apply` for every code change - use the fast path,
which bypasses Terraform entirely:

```bash
LAMBDA_FUNCTION_NAME=quote-aws-lambda-python ./scripts/deploy_code.sh
```

This rebuilds `build/lambda.zip` and does
`update-function-code` → `wait function-updated` → `publish-version` →
`update-alias --name live`, mirroring the two-stage deploy pattern used by
the quote-lambda-tf-backend reference (Terraform owns infra + the first
upload; routine deploys are a fast, separate path).

## Local development

There's no fully faithful local Cognito emulator. Two options:

- **Point local dev at the real deployed Cognito pool** (`COGNITO_USER_POOL_ID`/
  `COGNITO_APP_CLIENT_ID` env vars, from `terraform output`) plus a local
  DynamoDB (e.g. `docker run -p 8000:8000 amazon/dynamodb-local` and point
  `boto3` at it - not wired up by default, since this is a low-traffic
  personal project and a single environment was an explicit design choice).
- **Run the automated test suite** (`uv run pytest`), which is fully
  offline via `moto` for both DynamoDB and Cognito - see
  `tests/conftest.py` for how the Cognito JWKS verification is made to
  work against moto (see the comment there: moto's own HTTP mocking
  doesn't cover `PyJWKClient`'s use of raw `urllib.request`, so tests hand
  it moto's known public JWKS content directly instead of doing a real
  fetch).

For a full click-through, `wsgi.py` runs the Flask app directly
(`FLASK_CONFIG=dev python wsgi.py` after setting the AWS/Cognito env vars
above and exporting real AWS credentials with access to the deployed
DynamoDB tables and Cognito pool).

## Gotcha: API Gateway throttling

`infrastructure/api_gateway.tf`'s stage `default_route_settings` sets
`throttling_burst_limit`/`throttling_rate_limit` explicitly
(`api_throttling_burst_limit`/`api_throttling_rate_limit` variables,
default 100/100). **Do not remove that block** - AWS defaults both to 0
when it's absent, and every single request gets a 429. `scripts/smoke_test.sh`
includes a burst-request check specifically to catch a regression here.

## What's deliberately out of scope

- S3 quote-cache (the Java reference has one; not needed at this app's scale).
- SnapStart (Python-eligible on Lambda now, but a zip-deployed Python
  Lambda's cold start is already fast; adopting it would need auditing
  module-level state like the cached JWKS client for snapshot-safety first).
- Hosted UI / social identity providers / Cognito Identity Pool (Flask
  calls Cognito's Admin API directly with its own Lambda execution role -
  see `auth-flow.md`).
- Multiple environments / Terraform workspaces.
- An API Gateway Cognito JWT authorizer (auth stays in Flask code to
  preserve the HTMX-aware failure responses - see `auth-flow.md`).
- Provisioned concurrency, WAF, or rate-limiting beyond API Gateway's
  built-in throttling.
