from playwright.sync_api import expect


def test_profile_shows_username_and_roles(logged_in_page, base_url, registered_user):
    # Email is deliberately not asserted here: moto's mocked Cognito ID
    # token never includes an `email` claim at all (verified by decoding
    # one directly - only cognito:username/cognito:groups are present),
    # so g.user.email is genuinely empty offline regardless of what the
    # app does - the same class of moto/AliasAttributes gap documented in
    # tests/test_auth.py. Verify the real email display against a
    # deployed stack instead (scripts/smoke_test.sh or a manual
    # click-through).
    username, _password, _email = registered_user
    page = logged_in_page
    page.goto("/profile")
    expect(page.locator(".profile-info")).to_contain_text(username)
    expect(page.locator(".profile-info")).to_contain_text("USER")
    expect(page.locator(".profile-info")).not_to_contain_text("ADMIN")


def test_change_password_success_shows_toast_and_new_password_works(page, base_url, registered_user):
    username, password, _email = registered_user
    page.context.request.post(f"{base_url}/auth/login", form={"username": username, "password": password})
    page.goto("/profile")
    page.click("summary:has-text('Change password')")
    page.fill('input[name="current_password"]', password)
    page.fill('input[name="new_password"]', "NewPassw0rd!45")
    page.fill('input[name="confirm_password"]', "NewPassw0rd!45")

    with page.expect_response(lambda r: "/auth/change-password" in r.url):
        page.click('button.btn-submit:has-text("Change Password")')
    expect(page.locator(".toast-success")).to_have_text("Password changed successfully")
    # Auto-dismiss fires ~3s after insertion, then a 300ms fade-out (see
    # app.js) - generous slack beyond that nominal ~3.3s for test-host load.
    expect(page.locator(".toast-success")).to_be_hidden(timeout=8000)

    login_response = page.context.request.post(
        f"{base_url}/auth/login", form={"username": username, "password": "NewPassw0rd!45"}
    )
    assert login_response.ok


def test_change_password_wrong_current_shows_error_toast(logged_in_page, base_url):
    page = logged_in_page
    page.goto("/profile")
    page.click("summary:has-text('Change password')")
    page.fill('input[name="current_password"]', "totally-wrong")
    page.fill('input[name="new_password"]', "NewPassw0rd!45")
    page.fill('input[name="confirm_password"]', "NewPassw0rd!45")

    with page.expect_response(lambda r: "/auth/change-password" in r.url):
        page.click('button.btn-submit:has-text("Change Password")')
    expect(page.locator(".toast-error")).to_have_text("Current password is incorrect")


def test_change_password_mismatch_shows_error_toast(logged_in_page, base_url):
    page = logged_in_page
    page.goto("/profile")
    page.click("summary:has-text('Change password')")
    page.fill('input[name="current_password"]', "Passw0rd!23")
    page.fill('input[name="new_password"]', "NewPassw0rd!45")
    page.fill('input[name="confirm_password"]', "SomethingDifferent!")

    with page.expect_response(lambda r: "/auth/change-password" in r.url):
        page.click('button.btn-submit:has-text("Change Password")')
    expect(page.locator(".toast-error")).to_have_text("New passwords do not match")


def test_delete_account_with_confirm_logs_out_and_account_is_gone(page, base_url, registered_user):
    username, password, _email = registered_user
    page.context.request.post(f"{base_url}/auth/login", form={"username": username, "password": password})
    page.goto("/profile")
    page.click("summary:has-text('Delete account')")
    page.fill('input[name="password"]', password)

    page.once("dialog", lambda d: d.accept())
    with page.expect_response(lambda r: "/auth/unregister" in r.url):
        page.click('button.btn-delete:has-text("Delete My Account")')

    expect(page).to_have_url(base_url + "/")
    expect(page.get_by_role("link", name="Sign In")).to_be_visible()

    login_response = page.context.request.post(f"{base_url}/auth/login", form={"username": username, "password": password})
    assert login_response.status == 401
