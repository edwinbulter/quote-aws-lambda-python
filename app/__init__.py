import os

import jwt
from flask import Flask, g

from app.config import CONFIG_BY_NAME


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)

    config_name = config_name or os.environ.get("FLASK_CONFIG", "dev")
    app.config.from_object(CONFIG_BY_NAME[config_name])

    from app.admin.routes import admin_bp
    from app.auth.routes import auth_bp
    from app.auth.seed import seed_bp
    from app.favourites.routes import favourites_bp
    from app.health.routes import health_bp
    from app.pages.routes import pages_bp
    from app.quotes.routes import quotes_bp
    from app.viewed.routes import viewed_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(seed_bp)
    app.register_blueprint(quotes_bp)
    app.register_blueprint(favourites_bp)
    app.register_blueprint(viewed_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    @app.before_request
    def load_current_user():
        """Cognito/JWT replacement for the source app's DB-backed session
        loader. Populates g.user/g.roles from a verified ID-token cookie,
        transparently refreshing an expired one via the refresh-token
        cookie (there's no browser-side silent refresh without a Hosted-UI
        SDK, so this request-time refresh is the closest equivalent)."""
        from app.auth import cognito_client, cookies
        from app.auth.jwt_verify import verify_token
        from app.models import CurrentUser

        g.user = None
        g.roles = set()

        id_token, refresh_token = cookies.read_tokens()
        if not id_token:
            return

        try:
            claims = verify_token(id_token)
        except jwt.ExpiredSignatureError:
            if not refresh_token:
                cookies.stash_clear()
                return
            try:
                tokens = cognito_client.refresh(refresh_token)
                claims = verify_token(tokens.id_token)
            except Exception:
                cookies.stash_clear()
                return
            cookies.stash_new_tokens(tokens.id_token, tokens.refresh_token)
        except Exception:
            cookies.stash_clear()
            return

        g.user = CurrentUser(
            username=claims.get("cognito:username") or claims["sub"],
            email=claims.get("email", ""),
            sub=claims["sub"],
        )
        g.roles = set(claims.get("cognito:groups", []))

    @app.after_request
    def apply_cookies(response):
        from app.auth.cookies import apply_stashed_cookies

        return apply_stashed_cookies(response)

    @app.context_processor
    def inject_globals():
        return {"current_user": g.get("user"), "current_roles": g.get("roles", set())}

    return app
