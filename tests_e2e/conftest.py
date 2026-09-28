from uuid import uuid4

import pytest
import requests

from tests_e2e.mock_server import start_mock_server

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Admin123!"
USER1_USERNAME = "user-1"
USER1_PASSWORD = "Hello-user-1"


@pytest.fixture(scope="session")
def mock_server():
    server = start_mock_server()
    yield server
    server.shutdown()


@pytest.fixture(scope="session")
def base_url(mock_server):
    """pytest-playwright resolves relative page.goto("/x") calls against
    this automatically when a `base_url` fixture is defined."""
    return mock_server.url


@pytest.fixture(scope="session")
def seed_demo_users(mock_server, base_url):
    """Seeds admin/Admin123! and user-1/Hello-user-1 once per session, via
    the same POST /seed-users a real fresh deployment is bootstrapped
    with (see CLAUDE.md's seed-users gotcha)."""
    response = requests.post(f"{base_url}/seed-users", timeout=10)
    response.raise_for_status()


@pytest.fixture
def unique_username() -> str:
    """A fresh username per test, so per-user state (likes, favourites,
    viewed history, progress) never collides across tests sharing the one
    long-lived mock_server. See doc/e2e-testing.md's isolation rules."""
    return f"e2e-{uuid4().hex[:12]}"


@pytest.fixture
def registered_user(base_url, unique_username):
    """Registers a brand-new unique user via a raw HTTP POST (not the UI)
    and returns (username, password, email) - for tests that need a
    logged-out registered account without exercising the registration UI
    itself."""
    password = "Passw0rd!23"
    email = f"{unique_username}@example.invalid"
    response = requests.post(
        f"{base_url}/auth/register",
        data={
            "username": unique_username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        timeout=10,
    )
    assert response.status_code == 201, response.text
    return unique_username, password, email


def _login_context(page, base_url: str, username: str, password: str):
    """Logs in via context.request (shares the browser context's cookie
    jar with `page`), so the HttpOnly id_token/refresh_token cookies are
    set without driving the login UI - for fixtures where login itself
    isn't the thing under test."""
    response = page.context.request.post(
        f"{base_url}/auth/login",
        form={"username": username, "password": password},
    )
    assert response.ok, response.text()
    page.goto(base_url + "/")
    return page


@pytest.fixture
def logged_in_page(page, base_url, registered_user):
    """A page authenticated as a fresh, uniquely-named USER. Default
    fixture for any test that mutates its own user-scoped state (likes,
    favourites, viewed history, profile)."""
    username, password, _ = registered_user
    return _login_context(page, base_url, username, password)


@pytest.fixture
def admin_page(page, base_url, seed_demo_users):
    """A page authenticated as the seeded admin/Admin123! account.
    Reserved for read-mostly / permission-check tests - never for tests
    that mutate admin's own roles, likes, favourites, or existence,
    except the self-protection tests (which are no-ops by design)."""
    return _login_context(page, base_url, ADMIN_USERNAME, ADMIN_PASSWORD)


@pytest.fixture
def user1_page(page, base_url, seed_demo_users):
    """A page authenticated as the seeded user-1/Hello-user-1 account.
    Reserved for read-mostly / cross-checking scenarios - tests that
    mutate this account's own likes/favourites/viewed state must use
    `logged_in_page` (a unique per-test user) instead."""
    return _login_context(page, base_url, USER1_USERNAME, USER1_PASSWORD)
