from tests.conftest import login_as


def _like_several(client, ids):
    for quote_id in ids:
        client.post(f"/quote/{quote_id}/like")


def _likes_by_quote_id(app, username="alice"):
    with app.app_context():
        from app.dynamo import user_likes_repo

        return {int(item["quoteId"]): int(item["order"]) for item in user_likes_repo.query_by_username(username)}


def test_reorder_swaps_only_neighbors(app, client, seed_quotes):
    login_as(client)
    _like_several(client, [1, 2, 3])

    response = client.put("/favourites/2/reorder", data={"direction": "up"})
    assert response.status_code == 200

    likes = _likes_by_quote_id(app)
    # quote 2 and quote 1 swapped; quote 3 untouched
    assert likes[2] < likes[1]
    assert likes[3] == max(likes.values())


def test_reorder_at_boundary_is_noop(app, client, seed_quotes):
    login_as(client)
    _like_several(client, [1, 2])

    before = _likes_by_quote_id(app)
    response = client.put("/favourites/1/reorder", data={"direction": "up"})
    assert response.status_code == 200
    after = _likes_by_quote_id(app)
    assert before == after


def test_delete_favourite(app, client, seed_quotes):
    login_as(client)
    _like_several(client, [1, 2])

    response = client.delete("/favourites/1")
    assert response.status_code == 200

    remaining = _likes_by_quote_id(app)
    assert list(remaining.keys()) == [2]
