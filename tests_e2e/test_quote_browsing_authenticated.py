from playwright.sync_api import expect


def test_home_serves_next_unseen_quote_for_authenticated_user(logged_in_page, base_url):
    page = logged_in_page
    expect(page.locator("#quote-actions")).to_have_attribute("data-authenticated", "true")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "1")


def test_new_quote_advances_to_next_quote(logged_in_page, base_url):
    page = logged_in_page
    with page.expect_response(lambda r: "/quote/new" in r.url):
        page.click("#new-quote-btn")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "2")


def test_like_then_unlike_updates_favourites_strip(logged_in_page, base_url):
    page = logged_in_page
    quote_text = page.locator("#quote-display .quote-text").text_content()

    with page.expect_response(lambda r: "/quote/1/like" in r.url):
        page.click("button.btn-like")
    expect(page.locator("button.btn-like")).to_be_disabled()

    with page.expect_response(lambda r: "/favourites/strip" in r.url):
        page.click("text=Favourite Quotes")
    expect(page.locator("#favourites-strip .message")).to_have_count(1)
    expect(page.locator("#favourites-strip .message")).to_contain_text(quote_text.strip("“”"))

    page.goto("/manage/favourites")
    with page.expect_response(lambda r: "/favourites/1" in r.url and r.request.method == "DELETE"):
        page.once("dialog", lambda d: d.accept())
        page.click("button.btn-delete")
    expect(page.locator(".favourites-table")).to_have_count(0)
    expect(page.locator(".empty-state")).to_be_visible()


def test_server_driven_navigation_first_next_previous_last(logged_in_page, base_url):
    """`Previous`/`Next`/`First`/`Last` browse within [1, last_quote_id],
    where last_quote_id is *this user's own* furthest-reached quote (their
    progress high-water-mark) - only "New Quote" advances that high-water
    mark; Next/Prev/First/Last never do. So `Next` is disabled right after
    any New-Quote click (you're always sitting at your own last_quote_id
    then), and `Last` jumps back to that same point, not the global max."""
    page = logged_in_page
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "1")
    expect(page.locator("button.btn-previous")).to_be_disabled()
    expect(page.locator("button.btn-next")).to_be_disabled()

    # Advance progress to quote 3 via New Quote (1 -> 2 -> 3). A brief
    # settle wait between clicks avoids racing the previous response's
    # #quote-actions oob swap (a fresh #new-quote-btn element) with the
    # next click.
    for _ in range(2):
        with page.expect_response(lambda r: "/quote/new" in r.url):
            page.click("#new-quote-btn")
        page.wait_for_timeout(100)
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "3")
    expect(page.locator("button.btn-next")).to_be_disabled()
    expect(page.locator("button.btn-previous")).to_be_enabled()

    with page.expect_response(lambda r: r.url.endswith("/quote/2")):
        page.click("button.btn-previous")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "2")
    expect(page.locator("button.btn-next")).to_be_enabled()

    with page.expect_response(lambda r: r.url.endswith("/quote/3")):
        page.click("button.btn-next")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "3")
    expect(page.locator("button.btn-next")).to_be_disabled()

    with page.expect_response(lambda r: r.url.endswith("/quote/1")):
        page.click("button.btn-first")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "1")
    expect(page.locator("button.btn-previous")).to_be_disabled()

    with page.expect_response(lambda r: r.url.endswith("/quote/3")):
        page.click("button.btn-last")
    expect(page.locator("#quote-actions")).to_have_attribute("data-quote-id", "3")
