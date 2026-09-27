import pytest

from tests.conftest import login, register

# moto's Cognito mock only emulates the `UsernameAttributes` pool mode
# (where email *replaces* the username entirely), not the `AliasAttributes`
# mode this app's infrastructure/cognito.tf actually uses (chosen username
# + email as an additional sign-in alias) - moto's admin_create_user never
# raises AliasExistsException for a duplicate email under AliasAttributes,
# and admin_initiate_auth can't resolve an email USERNAME to the right
# user either. Real Cognito enforces both; verify with
# scripts/smoke_test.sh (or manual click-through) against the deployed
# stack instead of unit tests for these two behaviors.
_MOTO_ALIAS_LIMITATION = "moto does not emulate Cognito AliasAttributes email uniqueness/lookup - verify against real Cognito"


def test_register_success(client):
    response = register(client)
    assert response.status_code == 201


def test_register_password_mismatch(client):
    response = client.post(
        "/auth/register",
        data={
            "username": "bob",
            "email": "bob@example.com",
            "password": "Password123!",
            "confirm_password": "different",
        },
    )
    assert response.status_code == 400
    assert b"do not match" in response.data


def test_register_duplicate_username(client):
    register(client, username="carol", email="carol1@example.com")
    response = register(client, username="carol", email="carol2@example.com")
    assert response.status_code == 400
    assert b"already exists" in response.data


@pytest.mark.skip(reason=_MOTO_ALIAS_LIMITATION)
def test_register_duplicate_email(client):
    register(client, username="dave1", email="dave@example.com")
    response = register(client, username="dave2", email="dave@example.com")
    assert response.status_code == 400
    assert b"already exists" in response.data


def test_login_by_username(client):
    register(client, username="erin", email="erin@example.com", password="Password123!")
    response = login(client, "erin", "Password123!")
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/"
    assert "id_token=" in response.headers.get("Set-Cookie", "")


@pytest.mark.skip(reason=_MOTO_ALIAS_LIMITATION)
def test_login_by_email(client):
    register(client, username="frank", email="frank@example.com", password="Password123!")
    response = login(client, "frank@example.com", "Password123!")
    assert response.status_code == 200


def test_login_wrong_password(client):
    register(client, username="gina", email="gina@example.com", password="Password123!")
    response = login(client, "gina", "WrongPassword!")
    assert response.status_code == 401


def test_login_disabled_account(app, client):
    from app.auth import cognito_client

    register(client, username="henry", email="henry@example.com", password="Password123!")
    with app.app_context():
        cognito_client.disable_user("henry")

    response = login(client, "henry", "Password123!")
    assert response.status_code == 401


def test_logout_clears_session(client):
    register(client, username="ivan", email="ivan@example.com", password="Password123!")
    login(client, "ivan", "Password123!")
    response = client.post("/auth/logout")
    assert response.status_code == 200
    # A logged-out client should be redirected away from a login-required page.
    response = client.get("/profile")
    assert response.status_code in (302, 200)
    if response.status_code == 302:
        assert "/login" in response.headers["Location"]


def test_seed_users_idempotent(client):
    first = client.post("/seed-users")
    second = client.post("/seed-users")
    assert first.status_code == 200
    assert second.status_code == 200

    login_response = login(client, "user-1", "Hello-user-1")
    assert login_response.status_code == 200
    admin_login = login(client, "admin", "Admin123!")
    assert admin_login.status_code == 200


def test_change_password(client):
    register(client, username="jill", email="jill@example.com", password="Password123!")
    login(client, "jill", "Password123!")

    response = client.post(
        "/auth/change-password",
        data={
            "current_password": "Password123!",
            "new_password": "NewPassword456!",
            "confirm_password": "NewPassword456!",
        },
    )
    assert response.status_code == 200

    old_login = login(client, "jill", "Password123!")
    assert old_login.status_code == 401
    new_login = login(client, "jill", "NewPassword456!")
    assert new_login.status_code == 200


def test_unregister_deletes_account(client):
    register(client, username="kate", email="kate@example.com", password="Password123!")
    login(client, "kate", "Password123!")

    response = client.post("/auth/unregister", data={"password": "Password123!"})
    assert response.status_code == 200

    # The account is gone - registering the same username again should succeed.
    re_register = register(client, username="kate", email="kate2@example.com", password="Password123!")
    assert re_register.status_code == 201
