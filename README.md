# quote-aws-lambda-python

A port of [quote-k8s-python](https://github.com/edwinbulter/quote-k8s-python)
(a Flask/HTMX quote-browsing app, originally deployed on Kubernetes with
SQLite and session-cookie auth) to run as a single AWS Lambda function,
backed by DynamoDB and AWS Cognito, provisioned with Terraform - following
the pattern established by [quote-lambda-tf](https://github.com/edwinbulter/quote-lambda-tf)'s
Java backend, but as one Lambda, one Terraform folder, and one AWS
environment.

Same app, same HTML/HTMX UI, same routes - the database and auth layers
are what changed, because a Lambda can't host a local SQLite file and
multiple concurrent Lambda instances need stateless, independently
verifiable auth.

## Docs

- [`doc/architecture.md`](doc/architecture.md) - what changed vs. the
  source app, and why
- [`doc/auth-flow.md`](doc/auth-flow.md) - Cognito auth design in detail
- [`doc/dynamodb-schema.md`](doc/dynamodb-schema.md) - table schemas,
  the quote-id counter, transactional like-count consistency
- [`doc/deployment.md`](doc/deployment.md) - first-time setup, routine
  deploys, local dev, gotchas
- [`doc/costs.md`](doc/costs.md) - expected AWS costs at low traffic
  volumes, and what would make them grow
- [`doc/test-api.http`](doc/test-api.http) - manual route-by-route testing
  (JetBrains HTTP Client / VS Code REST Client), env selector in
  [`doc/http-client.env.json`](doc/http-client.env.json)
- [`infrastructure/README.md`](infrastructure/README.md) - Terraform specifics

## Quick start

```bash
uv sync                    # install app + dev dependencies
uv run pytest              # run the test suite (offline, via moto)
uv run ruff check .        # lint
```

```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
../scripts/build_lambda_package.sh
terraform init && terraform apply
```

See [`doc/deployment.md`](doc/deployment.md) for the full walkthrough,
including seeding demo accounts and the post-deploy smoke test.

## Layout

```
app/              Flask application (blueprints, DynamoDB repos, Cognito client, JWT verification)
infrastructure/   Terraform: DynamoDB, Cognito, Lambda, API Gateway, IAM, CloudWatch
scripts/          build/deploy/smoke-test scripts
tests/            pytest suite (moto-mocked DynamoDB + Cognito)
doc/              design docs
```
