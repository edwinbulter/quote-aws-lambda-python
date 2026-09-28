# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project overview

`quote-aws-lambda-python` is a port of
[quote-k8s-python](https://github.com/edwinbulter/quote-k8s-python) (a
Flask + HTMX quote-browsing monolith, originally on Kubernetes with SQLite
and session-cookie auth) to run as a **single AWS Lambda function**,
backed by **DynamoDB** and **AWS Cognito**, provisioned by **Terraform** -
following the architecture pattern of
[quote-lambda-tf](https://github.com/edwinbulter/quote-lambda-tf)'s Java
backend, but collapsed into one Lambda, one Terraform folder, one AWS
environment.

For the full architecture (what changed vs. the source app and why, the
DynamoDB schema, the Cognito auth flow, deployment) see
**`doc/architecture.md`**, **`doc/dynamodb-schema.md`**, **`doc/auth-flow.md`**,
**`doc/deployment.md`**, and **`doc/e2e-testing.md`** (Playwright browser
tests) - read the relevant one before making non-trivial changes.

## Commands

```bash
uv sync                        # install dependencies
uv run pytest                  # run tests (offline, via moto) - only tests/, not tests_e2e/
uv run pytest --cov=app        # with coverage
uv run ruff check .            # lint
FLASK_CONFIG=dev uv run python wsgi.py   # local dev server (needs real AWS creds + Cognito/DynamoDB env vars - see doc/deployment.md)
```

```bash
uv run playwright install chromium   # one-time, after `uv sync --group dev`
uv run pytest tests_e2e/             # Playwright browser e2e tests (slow, opt-in) - see doc/e2e-testing.md
uv run pytest tests_e2e/test_x.py -k y --headed --slowmo=1000   # step through visually
PWDEBUG=1 uv run pytest tests_e2e/test_x.py -k y                 # Playwright Inspector
```

```bash
cd infrastructure && terraform fmt -recursive && terraform validate
```

## Gotchas

- **`terraform plan`/`apply` fails with `filebase64sha256: no such file or
  directory` on `build/lambda.zip`** if you skip
  `scripts/build_lambda_package.sh` first - `aws_lambda_function` needs a
  real zip to hash at plan/apply time, not just at first apply. Run the
  build script (or `scripts/deploy_infra.sh`, which does it for you)
  before every `terraform plan`/`apply` where the zip might be missing or
  stale. The script uses `uv pip install --python-platform
  aarch64-manylinux2014 ...` (not bare `pip`, which isn't guaranteed to
  be on `PATH` and, even when present, may be an unrelated system Python).
- **API Gateway throttling defaults to 0 if `default_route_settings` is
  ever removed from `infrastructure/api_gateway.tf`** - every request
  429s. `scripts/smoke_test.sh` has a burst-request regression check for
  this specifically.
- **`aws_lambda_function` needs a real zip at `terraform apply` time.**
  Run `scripts/build_lambda_package.sh` first (or use
  `scripts/deploy_infra.sh`, which does it for you). Routine code changes
  after that should go through `scripts/deploy_code.sh`, not
  `terraform apply` - it's the fast path (`update-function-code` +
  `publish-version` + `update-alias`) and matches the two-stage deploy
  pattern used by the quote-lambda-tf-backend reference.
- **`POST /seed-users`** is an unauthenticated dev-only endpoint (gated by
  `SEED_USERS_ENABLED`, default on) that seeds `admin`/`Admin123!`
  (ADMIN) and `user-1`/`Hello-user-1` (USER) via Cognito Admin* calls.
  Disable it for anything production-facing. `tests_e2e/mock_server.py`
  relies on this defaulting to on in `TestConfig`.
- **`uv run pytest` only collects `tests/`** (`testpaths = ["tests"]` in
  `pyproject.toml`) - `tests_e2e/` (Playwright) must be targeted
  explicitly (`uv run pytest tests_e2e/`), see `doc/e2e-testing.md`.
- **htmx's default `responseHandling` skips the swap entirely for any
  4xx/5xx response** (including out-of-band toast swaps), which silently
  swallowed this app's inline validation errors and error toasts (login
  failure, registration errors, change-password errors, ...) - fixed by
  an override in `app/static/js/app.js`. If a new error-returning route's
  fragment isn't appearing in the browser, check that override is still
  in place before assuming the route itself is broken.
- **`hx-swap-oob="beforeend:#toast-container"` on the toast element
  itself would discard the element's own tag/class**, keeping only its
  text content (htmx's positional-selector OOB syntax inserts an
  OOB-tagged element's *content*, not the element) - `partials/toast.html`
  nests the styled `.toast` div one level inside a throwaway OOB wrapper
  to work around this. Keep that nesting if you touch toast rendering, or
  toasts go back to being unstyled text that never auto-dismisses.
- **Two of `tests/test_auth.py`'s tests are `@pytest.mark.skip`'d**
  (duplicate-email registration, login-by-email) because moto's Cognito
  mock doesn't emulate the `AliasAttributes` pool mode this app actually
  uses (only `UsernameAttributes`, a different config) - see the comment
  at the top of that file. These two behaviors are real and correct
  against actual Cognito; verify them with `scripts/smoke_test.sh` or a
  manual click-through against a deployed stack, not unit tests.
- **`tests/conftest.py` patches `PyJWKClient.fetch_data`** to hand back
  moto's fixed public JWKS content directly instead of doing a real HTTP
  fetch - moto's own request mocking doesn't cover `PyJWKClient`'s use of
  raw `urllib.request`, only `requests`/urllib3. If Cognito/JWT tests
  start doing real network calls, this is the first place to check.
- **`TransactWriteItems` calls go through `aws_clients.dynamodb_client()`
  (a plain low-level client), never `dynamodb_resource().meta.client`.**
  The resource's client carries an automatic type-conversion transform
  that double-processes the already-serialized items
  `app/dynamo/transact.py` builds and fails with a cryptic
  `TransactionCanceledException [TypeError, TypeError]`. If you see that
  error, check which client a new transactional call is using.
- Templates/static assets under `app/templates/`, `app/static/` are
  copied verbatim from the source app. `app/models.py` dataclasses
  deliberately mirror the old SQLAlchemy models' field names (`quote_id`,
  `quote_text`, `like_count`, ...) so those templates need zero edits -
  keep new fields consistent with that naming if you touch them.
