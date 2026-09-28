"""Moto/Flask setup shared by the in-process pytest suite (tests/conftest.py,
via FlaskClient) and the live-server Playwright suite (tests_e2e/mock_server.py,
via a real listening HTTP server) - one source of truth for "how do we stand
up a fully offline, moto-mocked DynamoDB + Cognito backend for this app"
instead of duplicating the setup in each.
"""

import os

import boto3
import jwt.jwks_client as _jwks_client_module
from moto.utilities.utils import load_resource

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_REGION", "eu-central-1")

# moto signs every Cognito ID/access token with one fixed built-in RSA
# keypair (same for every mocked user pool) and serves the matching public
# JWKS at the real `.well-known/jwks.json` path *within* its own HTTP
# mocking - but that mocking only intercepts the `requests`/urllib3 stack,
# not the raw `urllib.request` calls PyJWKClient makes internally, so a
# real network round trip to a nonexistent pool on real AWS 404s. Since
# moto's signing key is fixed and public, callers skip the network fetch
# entirely and hand PyJWKClient that same JWKS content directly.
_MOTO_JWKS = load_resource("cognitoidp/resources/jwks-public.json")


def patch_jwks_client() -> None:
    _jwks_client_module.PyJWKClient.fetch_data = lambda self: _MOTO_JWKS


def create_tables(flask_app) -> None:
    region = flask_app.config["AWS_REGION"]
    resource = boto3.resource("dynamodb", region_name=region)

    resource.create_table(
        TableName=flask_app.config["QUOTES_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "id", "AttributeType": "N"},
            {"AttributeName": "author", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "AuthorIndex",
                "KeySchema": [{"AttributeName": "author", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )

    resource.create_table(
        TableName=flask_app.config["USER_LIKES_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "username", "KeyType": "HASH"},
            {"AttributeName": "quoteId", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "username", "AttributeType": "S"},
            {"AttributeName": "quoteId", "AttributeType": "N"},
            {"AttributeName": "likedAt", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "QuoteIdIndex",
                "KeySchema": [
                    {"AttributeName": "quoteId", "KeyType": "HASH"},
                    {"AttributeName": "likedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )

    resource.create_table(
        TableName=flask_app.config["USER_PROGRESS_TABLE"],
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "username", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "username", "AttributeType": "S"},
            {"AttributeName": "lastQuoteId", "AttributeType": "N"},
            {"AttributeName": "updatedAt", "AttributeType": "N"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "LastQuoteIdIndex",
                "KeySchema": [
                    {"AttributeName": "lastQuoteId", "KeyType": "HASH"},
                    {"AttributeName": "updatedAt", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )


def create_user_pool(region: str) -> tuple[str, str]:
    client = boto3.client("cognito-idp", region_name=region)
    pool = client.create_user_pool(
        PoolName="test-pool",
        AliasAttributes=["email"],
        AutoVerifiedAttributes=["email"],
    )
    pool_id = pool["UserPool"]["Id"]

    app_client = client.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName="test-client",
        ExplicitAuthFlows=["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    )
    client_id = app_client["UserPoolClient"]["ClientId"]

    client.create_group(UserPoolId=pool_id, GroupName="USER", Precedence=10)
    client.create_group(UserPoolId=pool_id, GroupName="ADMIN", Precedence=1)

    return pool_id, client_id


def seed_quotes(flask_app, count: int = 10) -> None:
    """Insert a small deterministic pool of quotes, bypassing ZenQuotes.
    Must be called with `flask_app`'s app context active."""
    from app.dynamo import quotes_repo

    entries = [(f"Test quote {i}", f"Author {i}") for i in range(1, count + 1)]
    quotes_repo.batch_put_new(entries, source="Local")


def neutralize_zen_quotes() -> None:
    """Monkeypatch the ZenQuotes integration to a safe offline no-op.

    `app/admin/service.py` and `app/quotes/service.py` both call this via
    `from app.services import zen_quotes; zen_quotes.fetch_many()`, so
    patching the module attribute affects both call sites. This is a
    defense-in-depth safety net for the live e2e server (which runs for a
    whole test session and could otherwise make a real internet call if a
    quote pool gets exhausted or a test accidentally exercises "Add Quotes
    from ZEN") - tests themselves must still not rely on it returning
    real data.
    """
    from app.services import zen_quotes

    zen_quotes.fetch_many = list
