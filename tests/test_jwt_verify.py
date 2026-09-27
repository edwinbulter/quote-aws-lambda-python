import json
import time

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm
from moto.utilities.utils import load_resource

from tests.conftest import login, register


def _moto_private_key():
    jwk = load_resource("cognitoidp/resources/jwks-private.json")
    return RSAAlgorithm.from_jwk(json.dumps(jwk))


def _mint_token(app, *, username="alice", sub="test-sub", aud=None, exp_offset=3600, groups=None):
    now = int(time.time())
    payload = {
        "iss": f"https://cognito-idp.{app.config['AWS_REGION']}.amazonaws.com/{app.config['COGNITO_USER_POOL_ID']}",
        "sub": sub,
        "aud": aud or app.config["COGNITO_APP_CLIENT_ID"],
        "token_use": "id",
        "iat": now,
        "auth_time": now,
        "exp": now + exp_offset,
        "cognito:username": username,
        "cognito:groups": groups or [],
    }
    return jwt.encode(payload, _moto_private_key(), algorithm="RS256", headers={"kid": "dummy"})


def test_jwks_fetched_once_and_cached(app, monkeypatch):
    import jwt.jwks_client as jwks_client_module

    from app.auth.jwt_verify import _jwk_client, verify_token

    _jwk_client.cache_clear()

    original_fetch = jwks_client_module.PyJWKClient.fetch_data
    calls = {"n": 0}

    def counting_fetch(self):
        calls["n"] += 1
        return original_fetch(self)

    monkeypatch.setattr(jwks_client_module.PyJWKClient, "fetch_data", counting_fetch)

    with app.app_context():
        token_a = _mint_token(app, sub="sub-a")
        token_b = _mint_token(app, sub="sub-b")
        verify_token(token_a)
        verify_token(token_b)

    assert calls["n"] == 1, "second verify_token() call should reuse the cached JWKS, not refetch"


def test_expired_token_raises_expired_signature_error(app):
    from app.auth.jwt_verify import verify_token

    with app.app_context():
        token = _mint_token(app, exp_offset=-10)
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_token(token)


def test_tampered_signature_rejected(app):
    from app.auth.jwt_verify import verify_token

    with app.app_context():
        token = _mint_token(app)
        header, payload, signature = token.split(".")
        tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        tampered = f"{header}.{payload}.{tampered_signature}"
        with pytest.raises(jwt.InvalidTokenError):
            verify_token(tampered)


def test_wrong_audience_rejected(app):
    from app.auth.jwt_verify import verify_token

    with app.app_context():
        token = _mint_token(app, aud="some-other-client-id")
        with pytest.raises(jwt.InvalidAudienceError):
            verify_token(token)


def test_expired_id_token_triggers_transparent_refresh(app, client):
    register(client, username="mia", email="mia@example.com", password="Password123!")
    login(client, "mia", "Password123!")

    with app.app_context():
        expired = _mint_token(app, username="mia", sub="mia-sub", exp_offset=-10)

    # Overwrite the valid id_token cookie with an expired one; the still-valid
    # refresh_token cookie from login() is left in place.
    client.set_cookie("id_token", expired)

    response = client.get("/profile")
    assert response.status_code == 200
    assert "id_token=" in response.headers.get("Set-Cookie", "")


def test_expired_id_token_with_no_refresh_token_falls_back_to_anonymous(app, client):
    register(client, username="nia", email="nia@example.com", password="Password123!")
    login(client, "nia", "Password123!")

    with app.app_context():
        expired = _mint_token(app, username="nia", sub="nia-sub", exp_offset=-10)

    client.set_cookie("id_token", expired)
    client.delete_cookie("refresh_token")

    response = client.get("/profile")
    assert response.status_code in (302, 200)
    if response.status_code == 302:
        assert "/login" in response.headers["Location"]
