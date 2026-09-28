from playwright.sync_api import expect


def _advance_to_quote(page, quote_id: int):
    """A freshly logged-in user starts on quote 1; click New Quote until
    their progress reaches `quote_id` (New Quote always advances by
    exactly one, sequentially, for a fresh user - see
    test_quote_browsing_authenticated.py)."""
    while int(page.locator("#quote-actions").get_attribute("data-quote-id")) < quote_id:
        with page.expect_response(lambda r: "/quote/new" in r.url):
            page.click("#new-quote-btn")
        page.wait_for_timeout(100)


def _like_current_quote(page):
    with page.expect_response(lambda r: "/like" in r.url):
        page.click("button.btn-like")


def test_favourites_strip_refresh_shows_liked_quotes(logged_in_page, base_url):
    page = logged_in_page
    _like_current_quote(page)  # quote 1
    _advance_to_quote(page, 2)
    _like_current_quote(page)  # quote 2

    with page.expect_response(lambda r: "/favourites/strip" in r.url):
        page.click("text=Favourite Quotes")
    expect(page.locator("#favourites-strip .message")).to_have_count(2)


def test_manage_favourites_reorder_up_down(logged_in_page, base_url):
    page = logged_in_page
    _like_current_quote(page)  # quote 1
    _advance_to_quote(page, 2)
    _like_current_quote(page)  # quote 2
    _advance_to_quote(page, 3)
    _like_current_quote(page)  # quote 3 - order: [1, 2, 3]

    page.goto("/manage/favourites")
    rows = page.locator(".favourites-table tbody tr")
    expect(rows).to_have_count(3)
    first_quote_text = rows.nth(0).locator(".quote-cell").text_content()
    second_quote_text = rows.nth(1).locator(".quote-cell").text_content()

    with page.expect_response(lambda r: "/reorder" in r.url):
        rows.nth(0).get_by_title("Move down").click()

    rows = page.locator(".favourites-table tbody tr")
    expect(rows.nth(0)).to_contain_text(second_quote_text)
    expect(rows.nth(1)).to_contain_text(first_quote_text)


def test_manage_favourites_reorder_disabled_at_ends(logged_in_page, base_url):
    page = logged_in_page
    _like_current_quote(page)
    _advance_to_quote(page, 2)
    _like_current_quote(page)

    page.goto("/manage/favourites")
    rows = page.locator(".favourites-table tbody tr")
    expect(rows.nth(0).get_by_title("Move up")).to_be_disabled()
    expect(rows.nth(-1).get_by_title("Move down")).to_be_disabled()


def test_manage_favourites_delete_with_confirm(logged_in_page, base_url):
    page = logged_in_page
    _like_current_quote(page)

    page.goto("/manage/favourites")
    expect(page.locator(".favourites-table tbody tr")).to_have_count(1)

    page.once("dialog", lambda d: d.accept())
    with page.expect_response(lambda r: r.request.method == "DELETE"):
        page.get_by_title("Delete").click()

    expect(page.locator(".favourites-table")).to_have_count(0)
    expect(page.locator(".empty-state")).to_be_visible()
