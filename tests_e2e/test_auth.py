import pytest
from playwright.sync_api import expect

# See tests/test_auth.py: moto's Cognito mock only emulates the
# `UsernameAttributes` pool mode, not the `AliasAttributes` mode this
# app's infrastructure/cognito.tf actually uses, so duplicate-email
# rejection can't be exercised offline here either. Verify against real
# Cognito via scripts/smoke_test.sh or a manual click-through instead.
_MOTO_ALIAS_LIMITATION = "moto does not emulate Cognito AliasAttributes email uniqueness - verify against real Cognito"


def test_home_page_loads_for_anonymous_visitor(page, base_url):
    page.goto("/")
    expect(page.locator("#quote-display")).to_be_visible()
    expect(page.locator("#quote-actions")).to_have_attribute("data-authenticated", "false")
    expect(page.locator(".btn-signin")).to_have_text("Sign In")


def test_register_success_shows_login_form_with_notice(page, base_url, unique_username):
    page.goto("/login?mode=register")
    page.fill('input[name="username"]', unique_username)
    page.fill('input[name="email"]', f"{unique_username}@example.invalid")
    page.fill('input[name="password"]', "Passw0rd!23")
    page.fill('input[name="confirm_password"]', "Passw0rd!23")
    page.click('button.btn-submit:has-text("Register")')

    expect(page.locator("#auth-form-container .notice")).to_have_text(
        "Registration successful. Please sign in."
    )
    expect(page.locator('button.btn-submit:has-text("Login")')).to_be_visible()
    expect(page.locator(".btn-signin")).to_have_text("Sign In")


def test_register_duplicate_username_shows_error(page, base_url, registered_user):
    username, _password, _email = registered_user
    page.goto("/login?mode=register")
    page.fill('input[name="username"]', username)
    page.fill('input[name="email"]', "someone-else@example.invalid")
    page.fill('input[name="password"]', "Passw0rd!23")
    page.fill('input[name="confirm_password"]', "Passw0rd!23")
    page.click('button.btn-submit:has-text("Register")')

    expect(page.locator("#auth-form-container .error")).to_have_text("Username already exists")
    expect(page.locator('button.btn-submit:has-text("Register")')).to_be_visible()


@pytest.mark.skip(reason=_MOTO_ALIAS_LIMITATION)
def test_register_duplicate_email_shows_error(page, base_url, registered_user):
    _username, _password, email = registered_user
    page.goto("/login?mode=register")
    page.fill('input[name="username"]', "another-" + _username)
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', "Passw0rd!23")
    page.fill('input[name="confirm_password"]', "Passw0rd!23")
    page.click('button.btn-submit:has-text("Register")')

    expect(page.locator("#auth-form-container .error")).to_have_text("Email already exists")


def test_register_password_mismatch_shows_error(page, base_url, unique_username):
    page.goto("/login?mode=register")
    page.fill('input[name="username"]', unique_username)
    page.fill('input[name="email"]', f"{unique_username}@example.invalid")
    page.fill('input[name="password"]', "Passw0rd!23")
    page.fill('input[name="confirm_password"]', "SomethingElse!")
    page.click('button.btn-submit:has-text("Register")')

    expect(page.locator("#auth-form-container .error")).to_have_text("Passwords do not match")


def test_register_blank_username_blocked_by_required_field(page, base_url):
    """The username input has the `required` HTML attribute, so a blank
    submit never reaches the server at all - the browser's native
    validation blocks it client-side (the server's own "All fields are
    required" check is unreachable through the UI, only via a direct
    API call, already covered by tests/test_auth.py)."""
    page.goto("/login?mode=register")
    page.fill('input[name="email"]', "someone@example.invalid")
    page.fill('input[name="password"]', "Passw0rd!23")
    page.fill('input[name="confirm_password"]', "Passw0rd!23")
    page.click('button.btn-submit:has-text("Register")')

    # No request round trip happens; the form is still up, unswapped.
    expect(page.locator('input[name="username"]:invalid')).to_have_count(1)
    expect(page.locator('button.btn-submit:has-text("Register")')).to_be_visible()
    expect(page.locator("#auth-form-container .error")).to_have_count(0)


def test_login_success_navigates_home(page, base_url, registered_user):
    username, password, _email = registered_user
    page.goto("/login")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button.btn-submit:has-text("Login")')

    expect(page).to_have_url(base_url + "/")
    expect(page.locator(".user-initial")).to_be_visible()
    # `.btn-signin` is shared by both the anonymous "Sign In" link and the
    # authenticated "Sign Out" button (see base.html), so disambiguate by role/text.
    expect(page.get_by_role("link", name="Sign In")).to_have_count(0)
    expect(page.get_by_role("button", name="Sign Out")).to_be_visible()


def test_login_invalid_credentials_shows_error(page, base_url, registered_user):
    username, _password, _email = registered_user
    page.goto("/login")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', "wrong-password")
    page.click('button.btn-submit:has-text("Login")')

    expect(page.locator("#auth-form-container .error")).to_have_text("Invalid username or password")
    expect(page).to_have_url(base_url + "/login")


def test_logout_reverts_nav_and_blocks_profile(logged_in_page, base_url):
    page = logged_in_page
    expect(page.locator(".user-initial")).to_be_visible()

    page.click('form[hx-post="/auth/logout"] button')
    expect(page).to_have_url(base_url + "/")
    expect(page.locator(".btn-signin")).to_have_text("Sign In")

    response = page.goto("/profile")
    assert response.status == 200
    expect(page).to_have_url(base_url + "/login")
