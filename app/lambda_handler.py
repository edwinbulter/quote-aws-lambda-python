"""AWS Lambda entrypoint. `app` and `handler` are built once at cold start
and reused across warm invocations (Flask app object, blueprints, and the
cached JWKS/boto3 clients created along the way)."""

from apig_wsgi import make_lambda_handler

from app import create_app

app = create_app("prod")
handler = make_lambda_handler(app, binary_support=True)
