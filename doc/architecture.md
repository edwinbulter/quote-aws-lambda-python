# Architecture

This is a port of [quote-k8s-python](https://github.com/edwinbulter/quote-k8s-python)
(a Flask/HTMX monolith on Kubernetes, SQLite/SQLAlchemy, session-cookie auth)
to run as a single AWS Lambda function, following the DynamoDB + Cognito +
Terraform pattern already used by [quote-lambda-tf](https://github.com/edwinbulter/quote-lambda-tf)'s
Java backend - but as one Lambda, one Terraform folder, one AWS environment.

```
Browser
  │  HTML/HTMX over HTTPS, id_token+refresh_token cookies
  ▼
API Gateway HTTP API (ANY /{proxy+})
  ▼
Lambda (apig-wsgi adapter → the same Flask app, unchanged blueprints/templates)
  │
  ├─ DynamoDB: quotes / user_likes / user_progress
  └─ Cognito: User Pool (USER/ADMIN groups) via Admin* APIs
```

## What changed vs. the source app, and why

| Concern | Source app | This port | Why |
|---|---|---|---|
| Database | SQLite via SQLAlchemy | DynamoDB (3 tables) | A Lambda has no persistent local disk/process for SQLite to live on. |
| Auth | Flask signed-session cookie, roles reloaded from DB every request | Cognito User Pool + verified ID-token cookie | Multiple Lambda instances run concurrently with no shared memory - auth state has to be stateless and independently verifiable per invocation. |
| Deployment | Docker image on Kubernetes | Zip + `apig-wsgi` on Lambda, behind API Gateway | Single Lambda, no cluster to operate. |
| Infra | k8s manifests | Terraform (`infrastructure/`) | Reproducible, matches the quote-lambda-tf pattern. |
| Environments | dev/prod configs | single environment | Explicitly requested - this is a personal project, not something needing environment isolation. |

What's **unchanged**: the Flask blueprint structure, all HTML templates and
static assets (copied verbatim), the HTMX fragment/full-page route
contracts (status codes, `HX-Redirect`, toast fragments), the quote-serving
business logic (sequential-for-authenticated / random-for-anonymous,
ZenQuotes backfill), and the `login_required`/`roles_required` decorators.

See also: [`auth-flow.md`](auth-flow.md), [`dynamodb-schema.md`](dynamodb-schema.md),
[`deployment.md`](deployment.md), and `../infrastructure/README.md`.

## Code layout

```
app/
  __init__.py          create_app(): blueprints, Cognito/JWT before_request, cookie after_request
  lambda_handler.py     apig-wsgi adapter - the actual Lambda entrypoint
  aws_clients.py         cached boto3 client/resource factories
  models.py               dataclasses mirroring the old SQLAlchemy model field names
  admin/, auth/, favourites/, health/, pages/, quotes/, viewed/   same blueprints as the source app
  auth/cognito_client.py  boto3 cognito-idp wrapper (register/login/change-password/roles/...)
  auth/jwt_verify.py       Cognito ID-token verification against the pool's JWKS
  auth/cookies.py           id_token/refresh_token HttpOnly cookie handling
  dynamo/                    quotes_repo / user_likes_repo / user_progress_repo + transact.py
  services/zen_quotes.py    unchanged external ZenQuotes client
  static/, templates/         copied verbatim from quote-k8s-python
infrastructure/          Terraform: DynamoDB, Cognito, Lambda, API Gateway, IAM, logs
scripts/                  build_lambda_package.sh, deploy_infra.sh, deploy_code.sh, smoke_test.sh
tests/                     pytest against moto-mocked DynamoDB + Cognito
```

## Deliberate improvements over the quote-lambda-tf-backend (Java) reference

- **JWTs are actually verified.** The Java reference decodes the Cognito
  JWT without checking its signature (trusting API Gateway/Cognito to have
  done it, which isn't wired up there either). This app verifies signature,
  issuer, audience and expiry against Cognito's JWKS on every request
  (`app/auth/jwt_verify.py`).
- **No table scan to generate quote ids.** The Java reference does a full
  `Scan` for `MAX(id)` on every new quote. This app uses an atomic
  DynamoDB counter item instead (see `dynamodb-schema.md`).
- **`delete-all` no longer leaves a stale like count.** The source Flask
  app's bulk-delete of `UserLike` rows bypassed the `like_count` decrement
  a normal unlike does. This port's per-item delete-all fixes that.
- **Consistent ZenQuotes dedup key.** The source app deduped by exact quote
  text in one place and by `(text.lower(), author.lower())` in another.
  This port normalizes both to the same key.
