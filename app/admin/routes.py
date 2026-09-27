from flask import Blueprint, Response, g, render_template, request

from app.admin import service
from app.auth import cognito_client
from app.auth.decorators import roles_required
from app.auth.routes import _delete_user_data

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _toast(message: str, toast_type: str = "success") -> str:
    return render_template("partials/toast.html", message=message, toast_type=toast_type)


def _render_users_table() -> str:
    users = service.list_users()
    return render_template("partials/admin_users_table.html", users=users, current_username=g.user.username)


def _render_user_row(username: str) -> str | None:
    users = {u.username: u for u in service.list_users()}
    user = users.get(username)
    if user is None:
        return None
    return render_template("partials/admin_user_row.html", user=user, current_username=g.user.username)


@admin_bp.route("/users/table", methods=["GET"])
@roles_required("ADMIN")
def users_table():
    return Response(_render_users_table(), status=200)


@admin_bp.route("/users/<username>/roles/<role>", methods=["POST"])
@roles_required("ADMIN")
def grant_role(username: str, role: str):
    if not cognito_client.user_exists(username):
        return Response(status=404)
    granted = service.grant_role(username, role, g.user.username)
    row = _render_user_row(username)
    if row is None:
        return Response(status=404)
    toast = _toast(f"Added {username} to {role.upper()}") if granted else ""
    return Response(row + toast, status=200)


@admin_bp.route("/users/<username>/roles/<role>", methods=["DELETE"])
@roles_required("ADMIN")
def revoke_role(username: str, role: str):
    role_upper = role.upper()
    if role_upper == "ADMIN" and username == g.user.username:
        row = _render_user_row(username)
        return Response((row or "") + _toast("Cannot remove yourself from ADMIN", "error"), status=200)

    revoked = service.revoke_role(username, role_upper)
    row = _render_user_row(username)
    if row is None:
        return Response(status=404)
    toast = _toast(f"Removed {username} from {role_upper}") if revoked else ""
    return Response(row + toast, status=200)


@admin_bp.route("/users/<username>", methods=["DELETE"])
@roles_required("ADMIN")
def delete_user(username: str):
    if username == g.user.username:
        return Response(_render_users_table() + _toast("Cannot delete your own account", "error"), status=200)

    if not cognito_client.user_exists(username):
        return Response(status=404)

    _delete_user_data(username)
    return Response(
        _render_users_table() + _toast(f'User "{username}" and all their data have been deleted'),
        status=200,
    )


def _quotes_query_args():
    page = request.args.get("page", 1, type=int) or 1
    page_size = request.args.get("page_size", 50, type=int) or 50
    quote_text = request.args.get("q", "").strip() or None
    author = request.args.get("author", "").strip() or None
    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "asc")
    return page, page_size, quote_text, author, sort_by, sort_order


@admin_bp.route("/quotes/table", methods=["GET"])
@roles_required("ADMIN")
def quotes_table():
    page, page_size, quote_text, author, sort_by, sort_order = _quotes_query_args()
    result = service.get_quotes(page, page_size, quote_text, author, sort_by, sort_order)
    html = render_template(
        "partials/admin_quotes_table.html",
        **result,
        quote_text=quote_text or "",
        author=author or "",
        total_likes=service.get_total_likes(),
    )
    return Response(html, status=200)


@admin_bp.route("/quotes/fetch-zen", methods=["POST"])
@roles_required("ADMIN")
def fetch_zen_quotes():
    added = service.fetch_and_add_new_quotes()
    result = service.get_quotes(1, 50, None, None, "id", "asc")
    html = render_template(
        "partials/admin_quotes_table.html",
        **result,
        quote_text="",
        author="",
        total_likes=service.get_total_likes(),
    )
    html += _toast(f"Successfully added {added} new quotes")
    return Response(html, status=200)
