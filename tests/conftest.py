import pytest
from moto import mock_aws

from tests_support.moto_setup import create_tables, create_user_pool, patch_jwks_client

patch_jwks_client()


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
            create_tables(application)
            pool_id, client_id = create_user_pool(application.config["AWS_REGION"])
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
