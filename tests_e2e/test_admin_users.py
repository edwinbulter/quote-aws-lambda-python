from playwright.sync_api import expect


def _row_for(page, username: str):
    return page.locator("tr", has=page.locator(".username-cell", has_text=username))


def test_grant_and_revoke_user_role(admin_page, base_url, registered_user):
    target_username, _password, _email = registered_user
    page = admin_page
    page.goto("/manage/users")
    row = _row_for(page, target_username)
    user_checkbox = row.locator("td.role-cell").nth(0).locator("input[type=checkbox]")
    expect(user_checkbox).to_be_checked()  # registration grants USER by default

    with page.expect_response(lambda r: f"/{target_username}/roles/USER" in r.url):
        user_checkbox.uncheck()
    row = _row_for(page, target_username)
    expect(row.locator("td.role-cell").nth(0).locator("input[type=checkbox]")).not_to_be_checked()
    expect(page.locator(".toast-success").last).to_have_text(f"Removed {target_username} from USER")

    row = _row_for(page, target_username)
    with page.expect_response(lambda r: f"/{target_username}/roles/USER" in r.url):
        row.locator("td.role-cell").nth(0).locator("input[type=checkbox]").check()
    row = _row_for(page, target_username)
    expect(row.locator("td.role-cell").nth(0).locator("input[type=checkbox]")).to_be_checked()
    expect(page.locator(".toast-success").last).to_have_text(f"Added {target_username} to USER")


def test_grant_and_revoke_admin_role(admin_page, base_url, registered_user):
    target_username, _password, _email = registered_user
    page = admin_page
    page.goto("/manage/users")
    row = _row_for(page, target_username)
    admin_checkbox = row.locator("td.role-cell").nth(1).locator("input[type=checkbox]")
    expect(admin_checkbox).not_to_be_checked()

    with page.expect_response(lambda r: f"/{target_username}/roles/ADMIN" in r.url):
        admin_checkbox.check()
    expect(page.locator(".toast-success").last).to_have_text(f"Added {target_username} to ADMIN")
    row = _row_for(page, target_username)
    expect(row.locator("td.role-cell").nth(1).locator("input[type=checkbox]")).to_be_checked()

    row = _row_for(page, target_username)
    with page.expect_response(lambda r: f"/{target_username}/roles/ADMIN" in r.url):
        row.locator("td.role-cell").nth(1).locator("input[type=checkbox]").uncheck()
    expect(page.locator(".toast-success").last).to_have_text(f"Removed {target_username} from ADMIN")


def test_delete_user(admin_page, base_url, registered_user):
    target_username, _password, _email = registered_user
    page = admin_page
    page.goto("/manage/users")
    row = _row_for(page, target_username)
    expect(row).to_have_count(1)

    page.once("dialog", lambda d: d.accept())
    with page.expect_response(lambda r: r.request.method == "DELETE" and f"/users/{target_username}" in r.url):
        row.locator("button.btn-delete").click()

    expect(page.locator(".toast-success").last).to_be_visible()
    expect(_row_for(page, target_username)).to_have_count(0)


def test_cannot_remove_own_admin_role(admin_page, base_url):
    page = admin_page
    page.goto("/manage/users")
    row = _row_for(page, "admin")
    admin_checkbox = row.locator("td.role-cell").nth(1).locator("input[type=checkbox]")
    expect(admin_checkbox).to_be_checked()
    expect(admin_checkbox).to_be_disabled()
    expect(admin_checkbox).to_have_attribute("title", "Cannot remove yourself from ADMIN")


def test_cannot_delete_self(admin_page, base_url):
    page = admin_page
    page.goto("/manage/users")
    row = _row_for(page, "admin")
    delete_button = row.locator("button.btn-delete")
    expect(delete_button).to_be_disabled()
    expect(delete_button).to_have_attribute("title", "Cannot delete yourself")
