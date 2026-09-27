"""HttpOnly cookies for the Cognito ID/refresh tokens.

Replaces Flask's signed-session cookie as the place auth state lives.
before_request (app/__init__.py) can't itself mutate response headers, so
it stashes what to do on `g` and an after_request hook here applies it -
this keeps "verify, maybe refresh, maybe issue new cookies" and "write
the Set-Cookie headers" cleanly separated.
"""

from flask import Response, current_app, g, request


def read_tokens() -> tuple[str | None, str | None]:
    id_token = request.cookies.get(current_app.config["ID_TOKEN_COOKIE"])
    refresh_token = request.cookies.get(current_app.config["REFRESH_TOKEN_COOKIE"])
    return id_token, refresh_token


def stash_new_tokens(id_token: str, refresh_token: str | None) -> None:
    g._new_auth_cookies = (id_token, refresh_token)


def stash_clear() -> None:
    g._clear_auth_cookies = True


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": current_app.config["SESSION_COOKIE_SECURE"],
        "samesite": current_app.config["SESSION_COOKIE_SAMESITE"],
        "path": "/",
    }


def set_auth_cookies(response: Response, id_token: str, refresh_token: str | None) -> None:
    kwargs = _cookie_kwargs()
    response.set_cookie(current_app.config["ID_TOKEN_COOKIE"], id_token, max_age=3600, **kwargs)
    if refresh_token:
        response.set_cookie(
            current_app.config["REFRESH_TOKEN_COOKIE"], refresh_token, max_age=30 * 24 * 3600, **kwargs
        )


def clear_auth_cookies(response: Response) -> None:
    kwargs = _cookie_kwargs()
    response.delete_cookie(current_app.config["ID_TOKEN_COOKIE"], **kwargs)
    response.delete_cookie(current_app.config["REFRESH_TOKEN_COOKIE"], **kwargs)


def apply_stashed_cookies(response: Response) -> Response:
    """after_request hook: apply whatever before_request decided about cookies."""
    new_tokens = g.pop("_new_auth_cookies", None)
    if new_tokens is not None:
        set_auth_cookies(response, *new_tokens)
    elif g.pop("_clear_auth_cookies", False):
        clear_auth_cookies(response)
    return response
