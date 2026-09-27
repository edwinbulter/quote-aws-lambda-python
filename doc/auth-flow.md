# Auth flow

Cognito is the identity/credential store (replacing the old `User`/
`UserRole` SQL tables) and its `USER`/`ADMIN` groups are the roles store.
Flask calls Cognito's **Admin API** directly (server-side, via the Lambda's
own execution role) - there is no Hosted UI, no OAuth redirect, and no
Identity Pool. This keeps the existing login/register templates and the
`login_required`/`roles_required` decorators essentially unchanged.

## Why a cookie, not an API Gateway Cognito authorizer

A JWT authorizer on API Gateway would return a hard 401 for a missing/bad
token, bypassing Flask entirely - which would break the app's HTMX-aware
failure contract (`login_required`/`roles_required` return `200` +
`HX-Redirect: /login`, or a toast fragment, never a bare 401/403, so a
partial-swap HTMX request can react to it). So auth verification happens
inside Flask, and the Cognito ID token + refresh token are carried in
HttpOnly, `SameSite=Lax`, cookies (`id_token`, `refresh_token`) instead of
an `Authorization` header.

## Route → Cognito API mapping

| Route | Cognito call(s) |
|---|---|
| `POST /auth/register` | `admin_create_user` (SUPPRESS email) → `admin_set_user_password(Permanent=True)` → `admin_add_user_to_group("USER")` |
| `POST /auth/login` | `admin_initiate_auth(AuthFlow="ADMIN_USER_PASSWORD_AUTH")` |
| `POST /auth/logout` | none - just clears both cookies |
| `POST /auth/change-password` | `admin_initiate_auth` (verifies current password) → `admin_set_user_password` |
| `POST /auth/unregister` | `admin_initiate_auth` (verify) → `admin_delete_user` + DynamoDB likes/progress cleanup |
| `POST/DELETE /admin/users/<u>/roles/<r>` | `admin_add_user_to_group` / `admin_remove_user_from_group` (idempotent, checked via `admin_list_groups_for_user` first) |
| `DELETE /admin/users/<u>` | `admin_delete_user` + DynamoDB cleanup (no password check - admin action) |
| `GET /admin/users/table`, `/manage/users` | `list_users_in_group("USER")` + `list_users_in_group("ADMIN")` + `list_users` (roster assembled from these, not per-user calls) |
| `POST /seed-users` (dev-flag-gated) | same Admin calls, seeding `admin`/ADMIN and `user-1`/USER |

`is_active`-style soft-disable maps to `admin_disable_user`/`admin_enable_user`.
**Caveat:** disabling a user doesn't revoke already-issued tokens - a
disabled user's existing ID token still verifies fine until it naturally
expires (≤1h), and their next refresh attempt then fails. This is a
weaker-but-bounded enforcement window than the source app's
every-request DB check; acceptable for this app, called out here in case
instant enforcement ever matters (the alternative would be an
`admin_get_user` check per request on ADMIN-guarded routes only).

## Request-time verification (`app/__init__.py` before_request)

1. Read the `id_token` cookie. Missing → anonymous (`g.user = None`).
2. `app/auth/jwt_verify.verify_token()` verifies the token's signature
   (against Cognito's JWKS, cached per `(region, pool_id)` via
   `functools.lru_cache` so a warm Lambda execution environment reuses it
   across invocations with no network call until the cache's internal
   1-hour lifespan expires), issuer, audience and expiry.
3. **Valid** → `g.user`/`g.roles` populated from the verified claims
   (`cognito:username`, `email`, `sub`, `cognito:groups`).
4. **Expired** → attempt `admin_initiate_auth(AuthFlow="REFRESH_TOKEN_AUTH")`
   using the `refresh_token` cookie. Success re-verifies the new ID token
   and stashes both new tokens for `after_request` to write as cookies
   (before_request can't itself set response headers). Failure (revoked/
   expired refresh token, or the user was disabled/deleted) → anonymous,
   both cookies cleared. This request-time refresh is the closest
   equivalent to browser-side silent refresh, since there's no Hosted-UI/
   Amplify JS doing that client-side here.
5. **Any other failure** (bad signature, wrong audience/issuer, malformed
   token) → anonymous, cookies cleared defensively.

`login_required`/`roles_required` (`app/auth/decorators.py`) only ever read
`g.user`/`g.roles` - copied verbatim from the source app, no changes needed.
