from playwright.sync_api import expect


def test_home_shows_a_quote_with_like_disabled(page, base_url):
    page.goto("/")
    expect(page.locator("#quote-display .quote-text")).to_be_visible()
    expect(page.locator("button.btn-like")).to_be_disabled()


def test_favourites_strip_empty_for_anonymous(page, base_url):
    # The #favourites-strip wrapper always renders (see
    # partials/favourites_strip.html); it's just empty of content -
    # no refresh button, no messages - when there's no current_user.
    page.goto("/")
    expect(page.locator("#favourites-strip .btn-favourites")).to_have_count(0)
    expect(page.locator("#favourites-strip .message, #favourites-strip .message-empty")).to_have_count(0)


def test_new_quote_button_fetches_a_quote_via_htmx(page, base_url):
    page.goto("/")
    first_id = page.locator("#quote-actions").get_attribute("data-quote-id")

    with page.expect_response(lambda r: "/quote/new" in r.url):
        page.click("#new-quote-btn")

    # app.js syncs #excluded-ids from the freshly-swapped #quote-actions
    # dataset on htmx:afterSettle, which fires after the HTTP response
    # Playwright already awaited above - so wait for that value to settle.
    excluded_locator = page.locator("#excluded-ids")
    expect(excluded_locator).not_to_have_value("")
    excluded = excluded_locator.input_value()
    assert first_id in excluded.split(",")


def test_anon_prev_first_disabled_at_start_next_last_enabled_after_browsing(page, base_url):
    page.goto("/")
    # Only one quote seen so far: at both ends of local history.
    expect(page.locator("#anon-previous-btn")).to_be_disabled()
    expect(page.locator("#anon-first-btn")).to_be_disabled()
    expect(page.locator("#anon-next-btn")).to_be_disabled()
    expect(page.locator("#anon-last-btn")).to_be_disabled()

    for _ in range(3):
        with page.expect_response(lambda r: "/quote/new" in r.url):
            page.click("#new-quote-btn")

    # Now sitting on the most-recently-fetched quote: Next/Last still
    # disabled (nothing "ahead" of it locally), but Previous/First enabled.
    expect(page.locator("#anon-previous-btn")).to_be_enabled()
    expect(page.locator("#anon-first-btn")).to_be_enabled()
    expect(page.locator("#anon-next-btn")).to_be_disabled()
    expect(page.locator("#anon-last-btn")).to_be_disabled()


def test_anon_prev_next_navigate_locally_without_network_requests(page, base_url):
    page.goto("/")
    for _ in range(2):
        with page.expect_response(lambda r: "/quote/new" in r.url):
            page.click("#new-quote-btn")

    text_before = page.locator("#quote-display .quote-text").text_content()

    quote_requests = []
    page.on("request", lambda r: quote_requests.append(r.url) if "/quote/" in r.url else None)

    page.click("#anon-previous-btn")
    text_after = page.locator("#quote-display .quote-text").text_content()

    assert text_after != text_before
    assert quote_requests == [], f"expected no network requests for local nav, got {quote_requests}"

    page.click("#anon-next-btn")
    expect(page.locator("#quote-display .quote-text")).to_have_text(text_before)
    assert quote_requests == []
