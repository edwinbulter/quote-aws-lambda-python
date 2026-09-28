"""Boots a real Flask HTTP server against a long-lived moto mock, for
Playwright end-to-end browser tests.

`wsgi.py`/`FLASK_CONFIG=dev` requires real AWS credentials and a real
Cognito pool (see doc/deployment.md), and the existing offline pytest
suite (tests/) only ever talks to the app in-process via Flask's test
client - neither gives Playwright a real URL to point a browser at. This
adapts tests_support/moto_setup.py's moto plumbing into an actual
TCP-listening process instead: one shared, long-lived `mock_aws()`
context with a real werkzeug server running on a background thread.
"""

import threading
from dataclasses import dataclass

from moto import mock_aws
from werkzeug.serving import BaseWSGIServer, make_server

from tests_support.moto_setup import (
    create_tables,
    create_user_pool,
    neutralize_zen_quotes,
    patch_jwks_client,
)
from tests_support.moto_setup import (
    seed_quotes as seed_quotes_data,
)

# 12, not the unit suite's 10, so the admin quote-management table's
# smallest page-size option (10) actually produces a second page -
# letting e2e pagination tests drive real Previous/Next clicks through
# the UI's own page-size <select> instead of a page_size no option offers.
SEEDED_QUOTE_COUNT = 12


@dataclass
class MockServer:
    url: str
    app: object
    _httpd: BaseWSGIServer
    _thread: threading.Thread
    _mock_aws_cm: object

    def shutdown(self) -> None:
        self._httpd.shutdown()
        self._thread.join(timeout=5)
        self._mock_aws_cm.stop()


def start_mock_server(host: str = "127.0.0.1", port: int = 0) -> MockServer:
    patch_jwks_client()

    mock_aws_cm = mock_aws()
    mock_aws_cm.start()  # held open for the server's lifetime, not a `with` block

    from app import aws_clients

    aws_clients.dynamodb_resource.cache_clear()
    aws_clients.dynamodb_client.cache_clear()
    aws_clients.cognito_idp_client.cache_clear()

    from app import create_app

    flask_app = create_app("test")  # TestConfig: SEED_USERS_ENABLED=True, fixed table names

    with flask_app.app_context():
        create_tables(flask_app)
        pool_id, client_id = create_user_pool(flask_app.config["AWS_REGION"])
        flask_app.config["COGNITO_USER_POOL_ID"] = pool_id
        flask_app.config["COGNITO_APP_CLIENT_ID"] = client_id
        seed_quotes_data(flask_app, count=SEEDED_QUOTE_COUNT)
        neutralize_zen_quotes()

    httpd = make_server(host, port, flask_app, threaded=True)
    actual_port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    return MockServer(
        url=f"http://{host}:{actual_port}",
        app=flask_app,
        _httpd=httpd,
        _thread=thread,
        _mock_aws_cm=mock_aws_cm,
    )
