from tests.conftest import login, login_as, register


def _login_as_admin(client):
    client.post("/seed-users")
    return login(client, "admin", "Admin123!")


def test_grant_role_idempotent(app, client):
    _login_as_admin(client)
    register(client, username="target", email="target@example.com")

    r1 = client.post("/admin/users/target/roles/ADMIN")
    r2 = client.post("/admin/users/target/roles/ADMIN")
    assert r1.status_code == 200
    assert r2.status_code == 200

    with app.app_context():
        from app.auth import cognito_client

        assert "ADMIN" in cognito_client.list_groups_for_user("target")


def test_cannot_revoke_own_admin_role(client):
    _login_as_admin(client)
    response = client.delete("/admin/users/admin/roles/ADMIN")
    assert response.status_code == 200
    assert b"Cannot remove yourself" in response.data or b"error" in response.data.lower()


def test_cannot_delete_own_account(app, client):
    _login_as_admin(client)
    response = client.delete("/admin/users/admin")
    assert response.status_code == 200

    with app.app_context():
        from app.auth import cognito_client

        assert cognito_client.user_exists("admin")


def test_delete_other_user_cascades(app, client, seed_quotes):
    _login_as_admin(client)

    other_client = app.test_client()
    login_as(other_client, username="target2", email="target2@example.com")
    other_client.post("/quote/new")
    other_client.post("/quote/1/like")

    with app.app_context():
        from app.auth import cognito_client

        assert cognito_client.user_exists("target2")

    response = client.delete("/admin/users/target2")
    assert response.status_code == 200

    with app.app_context():
        from app.auth import cognito_client
        from app.dynamo import user_likes_repo, user_progress_repo

        assert not cognito_client.user_exists("target2")
        assert user_likes_repo.query_by_username("target2") == []
        assert user_progress_repo.get("target2") is None


def test_non_admin_cannot_access_admin_routes(client):
    login_as(client, username="plain", email="plain@example.com")
    response = client.get("/admin/users/table")
    assert response.status_code == 403
