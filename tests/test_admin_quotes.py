from tests.conftest import login


def _login_as_admin(client):
    client.post("/seed-users")
    return login(client, "admin", "Admin123!")


def test_search_case_insensitive(app, seed_quotes):
    from app.admin import service

    with app.app_context():
        result = service.get_quotes(1, 50, "TEST QUOTE 1", None, "id", "asc")
        texts = [q.quote_text for q in result["quotes"]]
        assert "Test quote 1" in texts


def test_sort_by_author_desc(app, seed_quotes):
    from app.admin import service

    with app.app_context():
        result = service.get_quotes(1, 50, None, None, "author", "desc")
        authors = [q.author for q in result["quotes"]]
        assert authors == sorted(authors, reverse=True)


def test_sort_by_likes_is_desc_only(app, seed_quotes):
    from app.admin import service

    with app.app_context():
        result = service.get_quotes(1, 50, None, None, "likes", "asc")
        assert result["sort_order"] == "desc"


def test_page_size_slicing(app, seed_quotes):
    from app.admin import service

    with app.app_context():
        result = service.get_quotes(1, 3, None, None, "id", "asc")
        assert len(result["quotes"]) == 3
        assert result["total_count"] == 10
        assert result["total_pages"] == 4

        page2 = service.get_quotes(2, 3, None, None, "id", "asc")
        assert [q.quote_id for q in page2["quotes"]] == [4, 5, 6]


def test_admin_quotes_table_route(client, seed_quotes):
    _login_as_admin(client)
    response = client.get("/admin/quotes/table?page=1&page_size=5&sort_by=id&sort_order=asc")
    assert response.status_code == 200
    assert b"Total Quotes" in response.data


def test_fetch_zen_dedups_by_normalized_text_and_author(app, client, seed_quotes):
    from unittest.mock import patch

    _login_as_admin(client)

    with patch("app.admin.service.zen_quotes.fetch_many") as mocked:
        mocked.return_value = [
            {"q": "Test quote 1", "a": "author 1"},  # duplicate, differs only by case
            {"q": "Brand new quote", "a": "New Author"},
        ]
        response = client.post("/admin/quotes/fetch-zen")
        assert response.status_code == 200
        assert b"added 1 new quote" in response.data.lower()

    with app.app_context():
        from app.dynamo import quotes_repo

        assert len(quotes_repo.scan_all()) == 11
