from functools import wraps

from flask import Response, g, redirect, request, url_for


def _is_htmx_request() -> bool:
    return request.headers.get("HX-Request") == "true"


def _unauthorized_response():
    if _is_htmx_request():
        return Response(status=200, headers={"HX-Redirect": url_for("pages.login")})
    return redirect(url_for("pages.login"))


def _forbidden_response(message: str):
    if _is_htmx_request():
        from flask import render_template

        html = render_template("partials/toast.html", message=message, toast_type="error")
        return Response(html, status=200)
    return Response(message, status=403)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return _unauthorized_response()
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.get("user") is None:
                return _unauthorized_response()
            if not (set(roles) & g.get("roles", set())):
                return _forbidden_response(f"{'/'.join(roles)} role required")
            return view(*args, **kwargs)

        return wrapped

    return decorator
