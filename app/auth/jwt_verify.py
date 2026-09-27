"""Cognito ID token verification against the pool's JWKS.

Fixes the known gap in the Java reference implementation (quote-lambda-tf
QuoteHandler decodes the JWT *without* verifying its signature, trusting
API Gateway/Cognito to have done it). Here every request verifies
signature + issuer + audience + expiry itself, since no API Gateway
Cognito authorizer is used (see doc/auth-flow.md for why).

The PyJWKClient is cached per (region, pool_id) via lru_cache so a warm
Lambda execution environment reuses it - and its own JWKS keys - across
invocations with zero network calls until its internal cache expires.
"""

from functools import lru_cache

import jwt
from jwt import PyJWKClient


def _issuer(region: str, pool_id: str) -> str:
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


@lru_cache(maxsize=4)
def _jwk_client(region: str, pool_id: str) -> PyJWKClient:
    jwks_url = f"{_issuer(region, pool_id)}/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def verify_token(id_token: str) -> dict:
    """Returns the verified claims dict, or raises a jwt.PyJWTError subclass
    (jwt.ExpiredSignatureError for an expired-but-otherwise-valid token,
    some other jwt.InvalidTokenError/PyJWKClientError for anything else
    invalid: bad signature, wrong audience/issuer, malformed token, ...).
    """
    from flask import current_app

    region = current_app.config["AWS_REGION"]
    pool_id = current_app.config["COGNITO_USER_POOL_ID"]
    client_id = current_app.config["COGNITO_APP_CLIENT_ID"]

    jwk_client = _jwk_client(region, pool_id)
    signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=client_id,
        issuer=_issuer(region, pool_id),
        options={"require": ["exp", "iat", "sub"]},
    )
