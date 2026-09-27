from tests.conftest import login_as


def test_toggle_like_from_viewed(app, client, seed_quotes):
    login_as(client)
    client.post("/quote/new")  # views quote 1

    r1 = client.post("/viewed/1/toggle-like")
    assert r1.status_code == 200
    assert b"Liked" in r1.data

    r2 = client.post("/viewed/1/toggle-like")
    assert r2.status_code == 200


def test_delete_all_resets_progress_and_decrements_like_count(app, client, seed_quotes):
    """Source app bug: bulk-deleting UserLike rows bypassed the like_count
    decrement unlike_quote() normally performs, leaving Quote.like_count
    stale. This port fixes that - delete-all must decrement it too."""
    login_as(client)
    client.post("/quote/new")  # views quote 1
    client.post("/quote/1/like")

    with app.app_context():
        from app.dynamo import quotes_repo

        assert quotes_repo.get_by_id(1).like_count == 1

    response = client.post("/viewed/delete-all")
    assert response.status_code == 200

    with app.app_context():
        from app.dynamo import quotes_repo, user_likes_repo, user_progress_repo

        assert quotes_repo.get_by_id(1).like_count == 0
        assert user_likes_repo.query_by_username("alice") == []
        progress = user_progress_repo.get("alice")
        assert progress.last_quote_id == 0
