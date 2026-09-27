from flask import Blueprint, Response, g, render_template, request, url_for

from app.auth import cognito_client, cookies
from app.auth.cognito_client import (
    EmailExistsError,
    InvalidCredentialsError,
    UsernameExistsError,
)
from app.auth.decorators import login_required
from app.dynamo import user_likes_repo, user_progress_repo

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _render_form(mode: str, error: str | None = None, values: dict | None = None, status: int = 200):
    html = render_template(
        "partials/auth_form_fragment.html",
        mode=mode,
        error=error,
        values=values or {},
    )
    return Response(html, status=status)


@auth_bp.route("/form", methods=["GET"])
def form():
    mode = request.args.get("mode", "login")
    if mode not in ("login", "register"):
        mode = "login"
    return _render_form(mode)


@auth_bp.route("/register", methods=["POST"])
def register():
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""
    values = {"username": username, "email": email}

    if not username or not email or not password:
        return _render_form("register", "All fields are required", values, status=400)
    if password != confirm_password:
        return _render_form("register", "Passwords do not match", values, status=400)

    try:
        cognito_client.register(username, email, password)
    except UsernameExistsError:
        return _render_form("register", "Username already exists", values, status=400)
    except EmailExistsError:
        return _render_form("register", "Email already exists", values, status=400)

    html = render_template(
        "partials/auth_form_fragment.html",
        mode="login",
        error=None,
        values={"username": username},
        notice="Registration successful. Please sign in.",
    )
    return Response(html, status=201)


@auth_bp.route("/login", methods=["POST"])
def login():
    identifier = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    try:
        tokens = cognito_client.authenticate(identifier, password)
    except InvalidCredentialsError:
        return _render_form("login", "Invalid username or password", {"username": identifier}, status=401)

    cookies.stash_new_tokens(tokens.id_token, tokens.refresh_token)
    return Response(status=200, headers={"HX-Redirect": url_for("pages.index")})


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    cookies.stash_clear()
    return Response(status=200, headers={"HX-Redirect": url_for("pages.index")})


@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    error = None
    if new_password != confirm_password:
        error = "New passwords do not match"
    elif not new_password:
        error = "New password is required"

    if not error:
        try:
            cognito_client.change_password(g.user.username, current_password, new_password)
        except InvalidCredentialsError:
            error = "Current password is incorrect"

    if error:
        html = render_template("partials/toast.html", message=error, toast_type="error")
        return Response(html, status=400)

    html = render_template("partials/toast.html", message="Password changed successfully", toast_type="success")
    return Response(html, status=200)


@auth_bp.route("/unregister", methods=["POST"])
@login_required
def unregister():
    password = request.form.get("password") or ""

    try:
        cognito_client.authenticate(g.user.username, password)
    except InvalidCredentialsError:
        html = render_template("partials/toast.html", message="Invalid password", toast_type="error")
        return Response(html, status=401)

    _delete_user_data(g.user.username)
    cookies.stash_clear()
    return Response(status=200, headers={"HX-Redirect": url_for("pages.index")})


def _delete_user_data(username: str) -> None:
    """Cascading delete shared by self-unregister, admin delete-user, and
    seed re-seeding. Removes the Cognito identity plus the DynamoDB rows
    Cognito has no concept of (likes, progress) - there's no `users`/
    `user_roles` table anymore, Cognito group membership goes away with
    the user itself."""
    cognito_client.delete_user(username)
    user_likes_repo.delete_all_for_user(username)
    user_progress_repo.delete(username)
