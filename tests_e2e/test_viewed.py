from playwright.sync_api import expect


def test_viewed_empty_state_for_new_user(page, base_url, registered_user):
    # logged_in_page always visits "/" first, which itself records quote 1
    # as viewed - to see the true empty state, log in without going home.
    username, password, _email = registered_user
    page.context.request.post(f"{base_url}/auth/login", form={"username": username, "password": password})
    page.goto("/manage/viewed")
    expect(page.locator(".empty-state")).to_be_visible()
    expect(page.get_by_role("button", name="Delete All")).to_have_count(0)


def test_viewed_table_lists_browsed_quotes(logged_in_page, base_url):
    page = logged_in_page  # already viewed quote 1 via the home-page load
    with page.expect_response(lambda r: "/quote/new" in r.url):
        page.click("#new-quote-btn")  # advances to quote 2

    page.goto("/manage/viewed")
    rows = page.locator(".viewed-quotes-table tbody tr")
    expect(rows).to_have_count(2)
    ids = [rows.nth(i).locator(".id-cell").text_content() for i in range(2)]
    assert set(ids) == {"1", "2"}


def test_viewed_row_like_toggle(logged_in_page, base_url):
    page = logged_in_page
    page.goto("/manage/viewed")
    toggle = page.locator(".viewed-quotes-table tbody tr").first.locator(".like-toggle-button")
    expect(toggle).to_contain_text("Like")

    with page.expect_response(lambda r: "toggle-like" in r.url):
        toggle.click()
    toggle = page.locator(".viewed-quotes-table tbody tr").first.locator(".like-toggle-button")
    expect(toggle).to_contain_text("Liked")
    expect(toggle).to_have_class("like-toggle-button liked")

    with page.expect_response(lambda r: "toggle-like" in r.url):
        toggle.click()
    toggle = page.locator(".viewed-quotes-table tbody tr").first.locator(".like-toggle-button")
    expect(toggle).to_contain_text("Like")
    expect(toggle).not_to_have_class("like-toggle-button liked")


def test_viewed_delete_all_with_confirm_clears_table(logged_in_page, base_url):
    page = logged_in_page
    with page.expect_response(lambda r: "/quote/new" in r.url):
        page.click("#new-quote-btn")

    page.goto("/manage/viewed")
    expect(page.locator(".viewed-quotes-table tbody tr")).to_have_count(2)

    page.once("dialog", lambda d: d.accept())
    with page.expect_response(lambda r: "/viewed/delete-all" in r.url):
        page.get_by_role("button", name="Delete All").click()

    expect(page.locator(".empty-state")).to_be_visible()
    expect(page.locator(".toast-success")).to_be_visible()

    # The AJAX response only swaps #viewed-table-container; the "Delete
    # All" button itself lives in the outer page template and isn't
    # touched by that swap, so it stays visible until a full reload even
    # though the table is now empty - reflects actual current behavior.
    expect(page.get_by_role("button", name="Delete All")).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="Delete All")).to_have_count(0)
