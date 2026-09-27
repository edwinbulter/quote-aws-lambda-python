import os

import boto3
import pytest
from moto import mock_aws
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
# moto's signing key is fixed and public, tests skip the network fetch
# entirely and hand PyJWKClient that same JWKS content directly.
import jwt.jwks_client as _jwks_client_module

_MOTO_JWKS = load_resource("cognitoidp/resources/jwks-public.json")
_jwks_client_module.PyJWKClient.fetch_data = lambda self: _MOTO_JWKS


def _create_tables(flask_app):
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


def _create_user_pool(region: str) -> tuple[str, str]:
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


@pytest.fixture
def app():
    with mock_aws():
        # boto3 clients are cached per-process (see app/aws_clients.py) so
        # each test needs fresh ones bound to this test's mock_aws context,
        # and jwt_verify's JWKS client cache is keyed by pool id, which is
        # freshly generated per test anyway.
        from app import aws_clients

        aws_clients.dynamodb_resource.cache_clear()
        aws_clients.dynamodb_client.cache_clear()
        aws_clients.cognito_idp_client.cache_clear()

        from app import create_app

        application = create_app("test")

        with application.app_context():
            _create_tables(application)
            pool_id, client_id = _create_user_pool(application.config["AWS_REGION"])
            application.config["COGNITO_USER_POOL_ID"] = pool_id
            application.config["COGNITO_APP_CLIENT_ID"] = client_id

        yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_quotes(app):
    """Insert a small deterministic pool of quotes, bypassing ZenQuotes."""
    from app.dynamo import quotes_repo

    with app.app_context():
        entries = [(f"Test quote {i}", f"Author {i}") for i in range(1, 11)]
        quotes_repo.batch_put_new(entries, source="Local")
    return app


def register(client, username="alice", email="alice@example.com", password="Password123!"):
    return client.post(
        "/auth/register",
        data={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )


def login(client, username, password):
    return client.post("/auth/login", data={"username": username, "password": password})


def login_as(client, username="alice", password="Password123!", email="alice@example.com"):
    register(client, username=username, email=email, password=password)
    return login(client, username, password)
