# Port quote-k8s-python to an AWS Lambda (quote-aws-lambda-python)

## Context

`quote-k8s-python` (github.com/edwinbulter/quote-k8s-python) is a Flask/HTMX monolith backed by SQLite/SQLAlchemy, running on Kubernetes, using Flask's signed-cookie session for login state (no JWT despite the name suggesting otherwise). Because a Lambda has no persistent local disk/process, the SQLite database can't come along — it needs to become DynamoDB. Because multiple Lambda instances can run concurrently with no shared memory, the session-cookie auth needs to become something stateless and verifiable per-invocation — AWS Cognito, following the pattern already proven in `quote-lambda-tf` (github.com/edwinbulter/quote-lambda-tf), which does this today with a Java backend + React frontend + split Terraform infra folders.

This project (`quote-aws-lambda-python`, currently an empty, non-git directory) reimplements the same app as **one Lambda function**, serving the same server-rendered HTML + HTMX fragments it does today (no JSON-API rewrite, no separate frontend), with **one Terraform infra folder** and **one application code folder**, and **a single AWS environment** (no dev/prod split, no Terraform workspaces).

Decisions already settled with the user (do not re-litigate):
1. **Cognito auth via secure cookie, not Hosted UI**: Flask's login route calls Cognito `AdminInitiateAuth` directly (boto3, server-side); the ID token + refresh token are stored in HttpOnly cookies; every request verifies the ID token's signature against Cognito's JWKS. This keeps the existing login/register/HTMX-aware-failure templates and `login_required`/`roles_required` decorators essentially unchanged, and fixes a real security gap in the Java reference (which decodes JWTs *without* verifying the signature).
2. **Zip deployment with a WSGI adapter** (`apig-wsgi`), not a container image — mirrors the reference's two-stage deploy (Terraform provisions infra + first upload; a script does fast `update-function-code`/`publish-version`/`update-alias` pushes after).
3. **DynamoDB atomic counter item** for quote-ID generation, replacing both SQLite autoincrement and the Java reference's known-weak full-table-scan-for-MAX(id) approach.

Research basis: two Explore agents fetched and analyzed the full `quote-k8s-python` source (routes, models, auth, business logic, ZenQuotes integration) and the full `quote-lambda-tf-backend` Terraform + Java architecture (DynamoDB schema, Cognito config, API Gateway wiring, IAM, deploy pattern), and a Plan agent turned that into the detailed design below. All three source repos referenced throughout this plan are **remote GitHub repos** (`edwinbulter/quote-k8s-python`, `edwinbulter/quote-lambda-tf`) — nothing from them exists locally; use `https://raw.githubusercontent.com/edwinbulter/<repo>/main/<path>` to pull specific files during implementation when needed.

---

## Target repo layout

```
quote-aws-lambda-python/
├── pyproject.toml, uv.lock, .python-version, .gitignore, README.md, CLAUDE.md
├── wsgi.py                          # local dev entrypoint
├── app/
│   ├── __init__.py                  # create_app(): config, blueprints, before_request auth (Cognito/JWT version)
│   ├── config.py                    # env-var driven config, no SQLALCHEMY_*
│   ├── aws_clients.py                # cached boto3 client/resource factories (warm-invocation reuse)
│   ├── models.py                     # dataclasses: Quote, LikedQuote, UserProgress, UserSummary — SAME field
│   │                                  # names as the old SQLAlchemy models so templates need zero edits
│   ├── lambda_handler.py             # apig-wsgi adapter — the actual Lambda entrypoint
│   ├── admin/{routes,service}.py     # Cognito list_users_in_group + DynamoDB scan/sort/filter/paginate
│   ├── auth/
│   │   ├── routes.py                 # register/login/logout/change-password/unregister
│   │   ├── decorators.py             # login_required / roles_required — UNCHANGED logic
│   │   ├── cognito_client.py         # thin wrapper over boto3 cognito-idp Admin* calls
│   │   ├── jwt_verify.py             # JWKS fetch/cache (PyJWKClient) + verify_token() + refresh-token renewal
│   │   ├── cookies.py                # set/clear id_token+refresh_token HttpOnly cookies, after_request hook
│   │   └── seed.py                   # /seed-users: Cognito AdminCreateUser + DynamoDB quote seeding
│   ├── favourites/routes.py
│   ├── health/routes.py              # /healthz -> cheap DynamoDB check
│   ├── pages/routes.py               # unchanged shape
│   ├── quotes/{routes,service}.py    # business logic, calls app/dynamo/*_repo.py
│   ├── viewed/routes.py
│   ├── services/zen_quotes.py        # copied verbatim, unchanged
│   ├── dynamo/
│   │   ├── quotes_repo.py            # get_by_id, batch_get, scan_all, next_id (counter), put_new
│   │   ├── user_likes_repo.py        # get, query_by_username, like/unlike (transactional), swap_order
│   │   └── user_progress_repo.py     # get, put_or_update
│   ├── static/, app/templates/       # copied verbatim from quote-k8s-python
├── infrastructure/
│   ├── backend.tf, provider.tf, variables.tf, locals.tf, outputs.tf
│   ├── dynamodb.tf, cognito.tf, iam.tf, lambda.tf, api_gateway.tf, cloudwatch.tf
│   ├── terraform.tfvars.example
│   └── artifacts/placeholder.zip     # stub for the very first `terraform apply`
├── scripts/
│   ├── build_lambda_package.sh       # pip install --platform ... --target build/ + zip
│   ├── deploy_code.sh                # fast path: update-function-code, publish-version, update-alias live
│   ├── deploy_infra.sh               # terraform init/plan/apply wrapper
│   └── smoke_test.sh                 # post-deploy curl-based E2E checks
├── tests/                            # pytest, moto for DynamoDB + Cognito, test-keypair JWKS fixture
└── doc/architecture.md, auth-flow.md, dynamodb-schema.md, deployment.md
```

---

## DynamoDB schema

Three tables (mirrors `quote-lambda-tf-backend`'s shape), all `PAY_PER_REQUEST`, `point_in_time_recovery` + `server_side_encryption` enabled. Considered a single-table design; rejected — this app's access patterns are simple point reads/writes with only one cross-entity write (like/unlike), which `TransactWriteItems` already handles cleanly across tables, so three small tables keep IAM/Terraform/mental-model simplicity with no real single-table payoff.

- **`quotes`**: PK `id` (N). Attrs: `quoteText` (S), `author` (S), `likeCount` (N), `source` (S), `createdAt` (N epoch-ms). GSI `AuthorIndex` (hash `author`, projection ALL, sparse).
  - **Counter item**: reserved item `{id: 0, counterValue: N}`. Next-id = `UpdateItem(id=0, ADD counterValue :n)` → returns the new id(s) atomically, no pre-seeding needed (DynamoDB inits the attribute to 0 on first `ADD`). `max_quote_id` = a single `GetItem(id=0)` — this fully replaces both SQLite autoincrement and the Java reference's `SELECT MAX(id)`/scan approach. Must be filtered out of admin `Scan`s (e.g. `attribute_exists(quoteText)`).
- **`user_likes`**: PK `username` (S), SK `quoteId` (N). Attrs: `order` (N), `likedAt` (N). GSI `QuoteIdIndex` (hash `quoteId`, range `likedAt`). Idempotent like via `ConditionExpression: attribute_not_exists(quoteId)`.
- **`user_progress`**: PK `username` (S). Attrs: `lastQuoteId` (N), `updatedAt` (N). GSI `LastQuoteIdIndex` (hash `lastQuoteId`, range `updatedAt`).
- **No `users`/`user_roles` tables** — Cognito (User Pool + `USER`/`ADMIN` groups) is the identity/roles store now; admin user listing is assembled at request time from Cognito (`list_users` + `list_users_in_group`).

**Atomicity**: like/unlike use `TransactWriteItems` (put-or-delete `user_likes` item + `UpdateItem` on `quotes.likeCount`, each with a `ConditionExpression` guard) to keep the denormalized counter consistent — this is the one place DynamoDB code differs meaningfully from the old single-`commit()` SQLAlchemy version. Favourite reorder (adjacent swap) is also a `TransactWriteItems` of two conditional `Update`s.

---

## Cognito design

- **User Pool**: `alias_attributes = ["email"]` (so username-or-email login works via one `USERNAME` param, matching the source's `"@" in identifier` branch), `auto_verified_attributes = ["email"]`, MFA off, password policy (8+ chars, upper/lower/number/symbol). No Hosted UI domain, no Google IdP, no Identity Pool — all excluded, unlike the Java reference (they're not needed for a server-side Flask app calling Admin APIs with its own Lambda execution role).
- **App Client**: `generate_secret = false`; `explicit_auth_flows = ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]` (server-side admin auth flow, not the browser-SDK SRP/USER_PASSWORD flows the reference uses); id/access token validity 1h, refresh 30d.
- **Groups**: `USER` (precedence 10), `ADMIN` (precedence 1) — replace the `UserRole` table entirely.
- **Route → Cognito call mapping** (all via boto3 `cognito-idp`):
  - register → `admin_create_user` + `admin_set_user_password(Permanent=True)` + `admin_add_user_to_group("USER")`
  - login → `admin_initiate_auth(AuthFlow="ADMIN_USER_PASSWORD_AUTH")`
  - change-password → `admin_initiate_auth` (verify current) + `admin_set_user_password`
  - unregister / admin-delete-user → `admin_initiate_auth`/none + `admin_delete_user` + DynamoDB cleanup (`Query`+`BatchWriteItem` delete `user_likes`, `DeleteItem` `user_progress`)
  - admin grant/revoke role → `admin_list_groups_for_user` (idempotency check) + `admin_add_user_to_group`/`admin_remove_user_from_group`
  - admin user listing → `list_users_in_group` ×2 (USER, ADMIN) + `list_users` — NOT one `admin_list_groups_for_user` call per user
  - `is_active` soft-disable → `admin_disable_user`/`admin_enable_user` (note: doesn't revoke already-issued tokens; disabled users fall back to anonymous within ≤1h when their ID token expires and refresh fails — an accepted, bounded weaker-than-before enforcement window, documented in `doc/auth-flow.md`)
  - `/seed-users` (dev-flag-gated, unchanged gate) → same Admin calls, seeding `admin`/ADMIN and `user-1`/USER, plus a small DynamoDB quote pool

---

## Request-auth verification (replaces `before_request` DB session-loader)

- Cookies: `id_token` + `refresh_token`, both HttpOnly/SameSite=Lax/Secure(env-toggled) — no more `SECRET_KEY`-signed Flask session for auth.
- `app/auth/jwt_verify.py`: a `PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)` created at **module import time**, so it's built once per cold start and reused across warm invocations with zero network calls until the cache expires.
- `verify_token(id_token)`: verifies signature, `issuer`, `audience`, `exp` via PyJWT against the cached JWKS — this is the fix for the Java reference's decode-without-verify gap.
- `before_request`: missing/invalid cookie → anonymous (`g.user=None`, `g.roles=set()`, same as today). Valid token → populate `g.user`/`g.roles` from verified claims (`cognito:username`, `email`, `sub`, `cognito:groups`). **Expired** token → attempt `admin_initiate_auth(AuthFlow="REFRESH_TOKEN_AUTH")` using the refresh-token cookie; success re-verifies and stashes new cookies for `after_request` to set (before_request can't mutate response headers itself); failure → treat as anonymous, clear both cookies.
- `login_required`/`roles_required` in `app/auth/decorators.py` need **no code changes** — they only ever read `g.user`/`g.roles`, so the existing HTMX-aware failure responses (200+`HX-Redirect`, toast fragments) keep working unmodified. This is exactly why auth stays in Flask code rather than an API Gateway Cognito JWT authorizer (which would return hard 401s and break that contract).

---

## Route/module migration map

| Blueprint | Preserved | Changed |
|---|---|---|
| `health` | route contract | SQL `SELECT 1` → cheap DynamoDB check |
| `pages` | entire route logic + templates | only object types changed (dataclasses, same field names) |
| `auth` | `decorators.py`, route URLs/statuses/HX-Redirect contract | `routes.py`/`seed.py` rewritten against `cognito_client.py`; session cookie → `cookies.py` |
| `quotes` | route surface, HTMX OOB response shapes | `service.py` rewritten against `app/dynamo/*_repo.py` |
| `favourites` | route surface | likes via `Query`+`BatchGetItem`; reorder/unlike via `TransactWriteItems` |
| `viewed` | route surface | delete-all now correctly decrements `likeCount` per deleted like — **intentional bug fix**: the source's bulk `.delete()` bypasses the counter decrement that `unlike_quote()` does; DynamoDB has no bulk "delete where," so the natural per-item port closes this gap. Flag as a deliberate behavior change. |
| `admin` | route surface, table/toast contract | user listing via Cognito; quote listing via full `Scan` + in-memory filter/sort/paginate (DynamoDB has no `ORDER BY`/`LIKE` — explicitly accepted as fine at this app's scale); fetch-zen dedup key normalized to `(text.lower(), author.lower())` consistently (source has this inconsistent between two call sites — fix during port) |

Random-quote-with-exclusions and sequential-next-quote logic port essentially 1:1, swapping SQLAlchemy calls for `GetItem`/counter reads; the "forward linear scan if a row was deleted" fallback and "full scan if exclusion pool nearly exhausted" fallback are preserved as explicit, accepted O(N) rare paths.

---

## Terraform (`infrastructure/`, single folder, single environment, no workspaces)

- **backend.tf**: S3 backend, same shared state bucket pattern as the reference (`edwinbulter-terraform-state`), key `quote-aws-lambda-python/terraform.tfstate`, no `workspace_key_prefix`.
- **variables.tf**: `aws_region`, `project_name`, three DynamoDB table-name vars, `lambda_memory_size`(512)/`timeout`(30)/`runtime`("python3.12")/`architecture`("arm64"), `lambda_zip_path`, `api_throttling_burst_limit`/`rate_limit` (100/100 — see gotcha below), `log_retention_days`, `seed_users_enabled`.
- **dynamodb.tf**: the 3 tables above.
- **cognito.tf**: User Pool + App Client + 2 groups, per the design above (deliberately smaller than the reference — no domain/IdP/identity pool).
- **iam.tf**: Lambda execution role; policy grants DynamoDB CRUD+Transact+Batch+Query+Scan on all 3 tables + their GSIs, Cognito Admin* actions + `ListUsers`/`ListUsersInGroup` on the pool ARN, CloudWatch Logs.
- **lambda.tf**: `aws_lambda_function` (zip, `handler = "app.lambda_handler.handler"`), `aws_lambda_alias.live`, `aws_lambda_permission` for API Gateway.
- **api_gateway.tf**: `aws_apigatewayv2_api` (HTTP, `ANY /{proxy+}`, AWS_PROXY to the `live` alias), `aws_apigatewayv2_stage` with **`default_route_settings.throttling_burst_limit`/`throttling_rate_limit` explicitly set** — ⚠️ carried-over gotcha from the reference: omitting this defaults both to 0 and every request 429s.
- **cloudwatch.tf**: Lambda + API Gateway log groups.
- **outputs.tf**: API Gateway invoke URL, Lambda name/ARN, table names/ARNs, Cognito pool/client IDs.
- **Bootstrap**: `aws_lambda_function` needs a real zip to exist at first `apply`. Build the real zip first via `scripts/build_lambda_package.sh` before the first `terraform apply` (mirrors the reference building its jar via Maven first), with `infrastructure/artifacts/placeholder.zip` available as a fallback stub if you want to stand up the infra skeleton before any app code exists.

---

## Packaging & deploy

- `app/lambda_handler.py`: `apig_wsgi.make_lambda_handler(create_app("prod"), binary_support=True)` — built once at cold start, reused warm.
- `scripts/build_lambda_package.sh`: `pip install --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 --only-binary=:all: --target build/` for the runtime deps (Flask, `apig-wsgi`, `PyJWT[crypto]`, `requests` — **not** boto3, it's preinstalled in the Lambda runtime), copy `app/`, zip to `build/lambda.zip`.
- Two-stage deploy, mirroring the Java reference exactly:
  1. `scripts/deploy_infra.sh` — rare, builds the zip once + `terraform apply` (provisions everything + first upload).
  2. `scripts/deploy_code.sh` — routine: `update-function-code` → `wait function-updated` → `publish-version` → `update-alias --name live`. Bypasses `terraform apply` for fast iteration.

---

## Testing

- pytest + Flask test client, moto (`mock_aws`) for both DynamoDB (tables created with the **exact** Terraform key/GSI schema, to catch drift) and Cognito (User Pool + Client + groups). Port existing test files' assertions largely as-is (route contracts unchanged); rewrite the fixture/setup layer.
- New `tests/test_jwt_verify.py`: JWKS cached-and-reused across calls, expired→refresh success/failure paths, tampered-token rejection. If moto's Cognito JWT fidelity proves insufficient, fall back to a test-only RSA keypair + `requests-mock`'d JWKS endpoint for this file specifically (Cognito Admin-API-driven tests elsewhere can keep using moto directly).
- `scripts/smoke_test.sh` against the real deployed API Gateway URL: anonymous `/`, seed-users, login (cookies present), sequential quote nav, like/unlike + favourites, admin role grant/revoke, `/healthz`, and a burst-request check with zero 429s (regression check for the throttling gotcha).

---

## Suggested implementation order

1. Repo skeleton + all of `infrastructure/*.tf`; copy `app/static/`+`app/templates/` verbatim; `terraform apply` with the placeholder zip to prove the whole stack (3 DynamoDB tables, Cognito pool/client/groups, IAM, Lambda+alias, API Gateway+throttling, log groups) stands up before any Flask code exists.
2. `app/dynamo/*_repo.py` + `app/models.py` dataclasses, unit-tested against moto with the same schema as the applied Terraform.
3. Auth layer (`cognito_client.py`, `jwt_verify.py`, `cookies.py`, `decorators.py` mostly copied, `routes.py`, `seed.py`), tested against moto Cognito + JWKS fixture.
4. `app/__init__.py` + `lambda_handler.py` + `config.py`; build/push first real zip; smoke-test `/healthz` + `/auth/*` against the live deployed URL.
5. Quotes core (new/get/like/unlike, counter-based IDs, sequential/random/backfill) — verify against the deployed stack.
6. Admin (Cognito-based user roster, DynamoDB scan/sort/filter/paginate, normalized fetch-zen dedup).
7. Favourites/viewed (transactional reorder/unlike, delete-all with the likeCount fix).
8. Pages blueprint + full template wiring; full pytest + `ruff` clean; full `scripts/smoke_test.sh` run.
9. Docs (`doc/architecture.md`, `auth-flow.md`, `dynamodb-schema.md`, `deployment.md`) + cold-start measurement to inform any future provisioned-concurrency decision.

## Explicitly out of scope

S3 quote-cache optimization (Java reference has it; not needed at this app's scale), SnapStart (Python-eligible now, but deferred — needs auditing module-level state like the cached JWKS client for snapshot-safety first), Google/social IdP + Hosted UI + Identity Pool, multi-environment/workspaces, API Gateway Cognito JWT authorizer, provisioned concurrency, WAF/extra rate-limiting beyond API Gateway's built-in throttling.

## Verification

- `pytest` + `ruff check` clean locally against moto-mocked AWS.
- `terraform -chdir=infrastructure plan`/`apply` succeeds and `terraform apply` again is a no-op (idempotent).
- `scripts/smoke_test.sh` passes end-to-end against the real deployed API Gateway URL, covering every route in the migration map plus the throttling-burst regression check.
- Manual click-through of the deployed URL: register → login → browse quotes (sequential as a logged-in user, random as anonymous) → like/reorder favourites → admin grant role → admin fetch-zen → logout.
