from flask import Blueprint, Response, g, render_template, request

from app.auth.decorators import login_required
from app.quotes import service

favourites_bp = Blueprint("favourites", __name__, url_prefix="/favourites")


def _render_table(toast_message: str | None = None, toast_type: str = "success") -> str:
    quotes = service.get_liked_quotes_for_user(g.user.username)
    html = render_template("partials/favourites_table.html", quotes=quotes)
    if toast_message:
        html += render_template("partials/toast.html", message=toast_message, toast_type=toast_type)
    return html


@favourites_bp.route("/strip", methods=["GET"])
@login_required
def strip():
    quotes = service.get_liked_quotes_for_user(g.user.username)
    html = render_template("partials/favourites_strip.html", quotes=quotes, oob=False)
    return Response(html, status=200)


@favourites_bp.route("/table", methods=["GET"])
@login_required
def table():
    return Response(_render_table(), status=200)


@favourites_bp.route("/<int:quote_id>/reorder", methods=["PUT"])
@login_required
def reorder(quote_id: int):
    direction = request.form.get("direction", "")
    moved = service.move_favourite(g.user.username, quote_id, direction)
    message = "Favourite reordered" if moved else None
    return Response(_render_table(message), status=200)


@favourites_bp.route("/<int:quote_id>", methods=["DELETE"])
@login_required
def delete(quote_id: int):
    service.unlike_quote(g.user.username, quote_id)
    return Response(_render_table("Favourite deleted"), status=200)
