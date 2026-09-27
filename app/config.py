import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    AWS_REGION = os.environ.get("AWS_REGION", "eu-central-1")

    QUOTES_TABLE = os.environ.get("QUOTES_TABLE", "quote-aws-lambda-quotes")
    USER_LIKES_TABLE = os.environ.get("USER_LIKES_TABLE", "quote-aws-lambda-user-likes")
    USER_PROGRESS_TABLE = os.environ.get("USER_PROGRESS_TABLE", "quote-aws-lambda-user-progress")

    COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
    COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")

    # Cookie names/flags for the Cognito ID/refresh tokens that replace the
    # Flask signed-session cookie (see app/auth/cookies.py, jwt_verify.py).
    ID_TOKEN_COOKIE = "id_token"
    REFRESH_TOKEN_COOKIE = "refresh_token"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_SAMESITE = "Lax"

    SEED_USERS_ENABLED = _bool_env("SEED_USERS_ENABLED", True)

    ZEN_QUOTES_TIMEOUT = float(os.environ.get("ZEN_QUOTES_TIMEOUT", "5"))
    ZEN_QUOTES_RETRIES = int(os.environ.get("ZEN_QUOTES_RETRIES", "2"))

    # Only needed so Flask has *a* secret key for flash-message signing;
    # auth state itself no longer lives in a signed Flask session.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")


class DevConfig(BaseConfig):
    DEBUG = True


class TestConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SEED_USERS_ENABLED = True
    AWS_REGION = "eu-central-1"
    QUOTES_TABLE = "quotes-test"
    USER_LIKES_TABLE = "user-likes-test"
    USER_PROGRESS_TABLE = "user-progress-test"


class ProdConfig(BaseConfig):
    DEBUG = False


CONFIG_BY_NAME = {
    "dev": DevConfig,
    "test": TestConfig,
    "prod": ProdConfig,
}
