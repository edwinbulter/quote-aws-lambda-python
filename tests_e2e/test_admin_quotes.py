"""Read-only against the 12 quotes seeded by tests_e2e/mock_server.py
("Test quote 1".."Test quote 12", "Author 1".."Author 12"). Never clicks
"Add Quotes from ZEN" - that POST /admin/quotes/fetch-zen makes a real
server-to-server HTTP call to zenquotes.io that Playwright's browser-level
network interception can't see or mock (it never goes through the
browser), so mock_server.py additionally neutralizes it as a safety net -
see doc/e2e-testing.md."""

from playwright.sync_api import expect


def test_search_by_quote_text(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    # hx-trigger="keyup changed delay:400ms" needs real keystrokes - fill()
    # only sets the value + fires "input", not "keyup".
    with page.expect_response(lambda r: "/admin/quotes/table" in r.url):
        page.locator('input[name="q"]').press_sequentially("Test quote 7", delay=20)
    rows = page.locator(".quotes-table tbody tr")
    expect(rows).to_have_count(1)
    expect(rows.first.locator(".quote-text-cell")).to_have_text("Test quote 7")


def test_search_by_author(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    with page.expect_response(lambda r: "/admin/quotes/table" in r.url):
        page.locator('input[name="author"]').press_sequentially("Author 3", delay=20)
    rows = page.locator(".quotes-table tbody tr")
    expect(rows).to_have_count(1)
    expect(rows.first.locator(".author-cell")).to_have_text("Author 3")


def test_sort_by_id_toggles_asc_desc(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    id_header = page.locator("th.sortable", has_text="ID")

    with page.expect_response(lambda r: "sort_by=id" in r.url and "sort_order=desc" in r.url):
        id_header.click()
    first_id_cell = page.locator(".quotes-table tbody tr").first.locator(".id-cell")
    expect(first_id_cell).to_have_text("12")

    id_header = page.locator("th.sortable", has_text="ID")
    with page.expect_response(lambda r: "sort_by=id" in r.url and "sort_order=asc" in r.url):
        id_header.click()
    first_id_cell = page.locator(".quotes-table tbody tr").first.locator(".id-cell")
    expect(first_id_cell).to_have_text("1")


def test_sort_by_likes_is_descending_only(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    with page.expect_response(lambda r: "sort_by=likes" in r.url):
        page.locator("th.sortable", has_text="Likes").click()
    # /manage/quotes' initial full-page load uses page_size=50 (see
    # app/pages/routes.py:manage_quotes), so all 12 seeded quotes fit on
    # one page.
    expect(page.locator(".quotes-table tbody tr")).to_have_count(12)


def test_pagination_previous_next(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    page_size_select = page.locator("select[name='page_size']")
    with page.expect_response(lambda r: "page_size=10" in r.url):
        page_size_select.select_option("10")

    expect(page.locator(".page-info")).to_have_text("Page 1 of 2")
    expect(page.get_by_role("button", name="Previous")).to_be_disabled()
    expect(page.locator(".quotes-table tbody tr")).to_have_count(10)

    with page.expect_response(lambda r: "page=2" in r.url):
        page.get_by_role("button", name="Next").click()
    expect(page.locator(".page-info")).to_have_text("Page 2 of 2")
    expect(page.locator(".quotes-table tbody tr")).to_have_count(2)
    expect(page.get_by_role("button", name="Next")).to_be_disabled()

    with page.expect_response(lambda r: "page=1" in r.url):
        page.get_by_role("button", name="Previous").click()
    expect(page.locator(".page-info")).to_have_text("Page 1 of 2")


def test_clear_button_resets_search_and_sort(admin_page, base_url):
    page = admin_page
    page.goto("/manage/quotes")
    with page.expect_response(lambda r: "/admin/quotes/table" in r.url):
        page.locator('input[name="q"]').press_sequentially("Test quote 7", delay=20)
    expect(page.locator(".quotes-table tbody tr")).to_have_count(1)

    with page.expect_response(lambda r: "/admin/quotes/table" in r.url):
        page.click(".clear-search-button")
    expect(page.locator('input[name="q"]')).to_have_value("")
    expect(page.locator(".quotes-table tbody tr")).to_have_count(12)
