# End-to-end (Playwright) testing

This document covers `tests_e2e/` - browser-driven Playwright tests that
exercise the actual rendered HTML, HTMX swaps, and client-side JS
(`app/static/js/app.js`) in a real Chromium browser. It's a separate
suite from `tests/` (fast, offline, in-process `FlaskClient` unit/
integration tests) - see the table in [Coverage map](#coverage-map) for
what's tested where.

Add a new test here when the thing under test is genuinely a *browser*
behavior - an HTMX swap actually landing in the DOM, a client-side JS
interaction (`app.js`'s anonymous quote navigation), a disabled-button
state, a `confirm()` dialog, CSS-class-driven UI state. Add it to
`tests/` instead when it's really about server logic/response content -
that suite is far faster and doesn't need a browser at all.

## Running the suite

```bash
uv sync --group dev
uv run playwright install chromium   # one-time browser binary install
uv run pytest tests_e2e/             # the whole e2e suite (slow, opt-in)
uv run pytest tests_e2e/test_favourites.py           # one file
uv run pytest tests_e2e/ -k reorder                  # by name substring
```

`uv run pytest` on its own only collects `tests/` (see
`[tool.pytest.ini_options] testpaths = ["tests"]` in `pyproject.toml`) -
`tests_e2e/` is always opt-in, since it's much slower (spins up a real
browser and a real HTTP server) and isn't part of the fast inner-loop
suite.

## Debug / headed / step-through mode

```bash
# Visible browser window instead of headless:
uv run pytest tests_e2e/test_favourites.py -k reorder --headed

# Visible + slowed down (1s pause between actions) - good for watching
# a whole flow play out:
uv run pytest tests_e2e/test_favourites.py -k reorder --headed --slowmo=1000

# Opens the Playwright Inspector, paused before the first action - step
# through, inspect selectors, re-run individual actions interactively:
PWDEBUG=1 uv run pytest tests_e2e/test_favourites.py -k reorder
```

You can also drop `page.pause()` anywhere inside a test body to break
into the Inspector at that exact point - e.g. to poke around the live
mocked app manually (`page.goto(base_url + "/manage/users")`, etc.)
mid-test. This is safe to leave in indefinitely: the mocked server
(`tests_e2e/mock_server.py`) is session-scoped, so it's still there
however long you stay paused - see [How the mocked server
works](#how-the-mocked-server-works).

Always scope a debug run with `-k <substring>` or a specific file/test
id. Pausing inside a full, unfiltered run blocks every test that would
otherwise run after the paused one.

## How the mocked server works

`wsgi.py`/`FLASK_CONFIG=dev` needs real AWS credentials and a real
deployed Cognito pool (see `doc/deployment.md`), and the offline `tests/`
suite only ever talks to the app in-process via Flask's test client -
neither gives Playwright a real URL to point a browser at.
`tests_e2e/mock_server.py` bridges that gap: it starts a real
`werkzeug` HTTP server, backed by a single long-lived `moto.mock_aws()`
context (DynamoDB + Cognito, entirely in-memory, no real AWS calls),
seeded with 12 deterministic quotes (`Test quote 1`.."`Test quote 12`",
`Author 1`.."`Author 12`") via the same helpers `tests/conftest.py` uses
(`tests_support/moto_setup.py`).

The server is **session-scoped** (`tests_e2e/conftest.py`'s `mock_server`
fixture) - started once for the whole e2e run, not per test or per file.
This is deliberate:

- Provisioning cost: moto's `create_user_pool` plus three DynamoDB
  `create_table` calls add real startup latency. Re-provisioning per test
  would slow the suite for no isolation benefit, because isolation is
  instead solved at the *data* layer (unique usernames - see [Test
  isolation conventions](#test-isolation-conventions)), not by tearing
  down infrastructure between tests.
- Debuggability: a function/module-scoped server would be torn down (or
  racing teardown from the *next* test's setup) the moment a developer
  pauses mid-test with `page.pause()`/`PWDEBUG=1`, killing the live
  request the paused browser is still making. Session scope means it's
  still there no matter how long you stay paused.

`admin`/`user-1` demo accounts are **not** pre-seeded at server startup -
they're created lazily, once per session, via `POST /seed-users` (the
same idempotent, unauthenticated-by-design endpoint a real fresh
deployment is bootstrapped with - see CLAUDE.md's seed-users gotcha),
the first time a test uses the `admin_page`/`user1_page` fixture.

## Test isolation conventions

All e2e tests share the one long-lived server for the whole session, so
state (likes, favourites, viewed history, role grants, quote data) can
leak between tests unless these conventions are followed:

1. **Any test that logs in and mutates its own state** (like/unlike,
   favourite/reorder/delete, viewed history, change password, delete
   account) uses the `registered_user`/`logged_in_page` fixtures - a
   fresh `uuid4`-suffixed username per test - **never** `admin`/`user-1`.
2. **`admin_page`/`user1_page` are for "some ADMIN account" / "some
   non-admin account" checks that don't mutate that account's own
   identity or roles** - role-gating checks, admin quote-table search/
   sort/pagination (read-only). Don't like a quote, change a password, or
   otherwise touch per-user state as `admin`/`user-1`, since other tests
   later in the session rely on them staying in their original state.
3. **Admin tests that grant/revoke roles or delete a user always target
   a freshly registered unique user** (via `registered_user`), acted on
   through a separate `admin_page` session - never `admin`/`user-1`
   themselves. The one exception: the two self-protection tests (can't
   remove your own ADMIN role, can't delete yourself) legitimately target
   `admin`'s own row, but are safe because the action is rejected and
   nothing actually changes.
4. **Never assert exact global counts** (total quotes, total users,
   total likes) - other tests sharing the session may have registered
   users, liked quotes, etc. Assert relative/local facts instead: "the
   row for `<my-unique-username>` now shows X", "this quote's like count
   increased by exactly 1 compared to a value read immediately before the
   action".
5. **The 12 seeded quotes are assumed to stay exactly 12** for the whole
   session - no test ever adds a quote (ZenQuotes is neutralized, see
   below, and there's no other quote-creation UI). If a future test ever
   needs to add quotes, this assumption - and the pagination/sort tests
   in `test_admin_quotes.py` that hardcode "12"/"2 pages at page_size=10"
   - will need revisiting.
6. Tests should not depend on execution order, even though the suite
   doesn't currently run in parallel - the conventions above are written
   so that adding parallelism later wouldn't silently break isolation.

## Known limitations

- **"Add Quotes from ZEN" is never clicked.** `POST
  /admin/quotes/fetch-zen` makes a real server-to-server HTTP call to
  `zenquotes.io` (see `app/services/zen_quotes.py`) - Playwright's
  browser-level network interception (`page.route()`) can't see or mock
  it, since it never goes through the browser's own network stack.
  `tests_e2e/mock_server.py` additionally monkeypatches
  `zen_quotes.fetch_many` to a safe offline no-op as defense-in-depth (in
  case a quote pool ever gets exhausted mid-session and the app tries an
  automatic refetch), but tests themselves must still never click that
  button.
- **Cognito `AliasAttributes` gaps carry over from `tests/`.** Just like
  `tests/test_auth.py` documents, moto's Cognito mock doesn't emulate
  the `AliasAttributes` pool mode this app actually uses (chosen
  username + email as an additional sign-in alias) - duplicate-email
  registration can't be verified offline. `test_auth.py`'s
  `test_register_duplicate_email_shows_error` is `@pytest.mark.skip`'d
  for the same reason, pointing back at that rationale rather than
  re-deriving a new one. Verify both against a real deployed stack
  (`scripts/smoke_test.sh` or a manual click-through).
- **The mocked ID token never carries an `email` claim.** Decoding one
  directly shows only `cognito:username`/`cognito:groups` - no `email` -
  so `g.user.email` is genuinely empty in this offline environment
  regardless of what the app does. `test_profile.py` only asserts
  username/roles for this reason; verify the profile page's email
  display against a real deployed stack instead.

## Adding a new e2e test

- Pick the right auth fixture: `logged_in_page` (fresh unique user, for
  anything that mutates that user's own state), `admin_page`/`user1_page`
  (shared seeded accounts, read-mostly/permission checks only), or a bare
  `page` for anonymous flows.
- Never assert global counts - see [Test isolation
  conventions](#test-isolation-conventions) above.
- A `confirm()` dialog (`hx-confirm="..."`) needs a
  `page.once("dialog", lambda d: d.accept())` registered *before* the
  click that triggers it.
- A successful login/logout/unregister response carries an `HX-Redirect`
  header, not a normal 3xx redirect - htmx does the navigation itself
  after the response lands, so assert with `expect(page).to_have_url(...)`
  (which retries) rather than assuming the navigation is synchronous with
  the click.
- Prefer role/text-based locators (`page.get_by_role(...)`) over shared
  CSS classes where two different elements can carry the same class -
  e.g. `.btn-signin` is used by both the anonymous "Sign In" link and the
  authenticated "Sign Out" button (see `app/templates/base.html`).

## Coverage map

| File | Covers |
| --- | --- |
| `test_auth.py` | Register (success, duplicate username, password mismatch, blank-field browser validation), login (success, invalid credentials), logout |
| `test_quote_browsing_anonymous.py` | Home page for an anonymous visitor, "New Quote", client-side Previous/Next/First/Last button state and local (no-network) navigation |
| `test_quote_browsing_authenticated.py` | "New Quote" advancing progress, like/unlike, server-driven Previous/Next/First/Last within `[1, last_quote_id]` |
| `test_favourites.py` | Favourites strip refresh, manage-favourites reorder (up/down, disabled at ends), delete with confirm |
| `test_viewed.py` | Viewed-quotes table, empty state, per-row like/unlike toggle, "Delete All" with confirm |
| `test_profile.py` | Profile info display, change password (success + error paths), delete account |
| `test_role_based_ui.py` | Management-menu link disabling for non-admins, direct-navigation guards (`403` for non-admin, redirect-to-login for anonymous) |
| `test_admin_users.py` | Grant/revoke USER and ADMIN roles, delete user, self-protection (can't remove own ADMIN / can't delete self) |
| `test_admin_quotes.py` | Search by text/author, sort by each column, pagination, clear-search - read-only, never fetches from ZenQuotes |
