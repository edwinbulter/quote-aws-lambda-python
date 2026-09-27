from flask import Blueprint, Response, g, render_template

from app.auth.decorators import login_required
from app.quotes import service

viewed_bp = Blueprint("viewed", __name__, url_prefix="/viewed")


@viewed_bp.route("/<int:quote_id>/toggle-like", methods=["POST"])
@login_required
def toggle_like(quote_id: int):
    username = g.user.username
    currently_liked = service.is_liked(username, quote_id)
    if currently_liked:
        quote = service.unlike_quote(username, quote_id)
    else:
        quote = service.like_quote(username, quote_id)

    if quote is None:
        return Response(status=404)

    html = render_template(
        "partials/viewed_row.html",
        quote=quote,
        is_liked=not currently_liked,
    )
    return Response(html, status=200)


@viewed_bp.route("/delete-all", methods=["POST"])
@login_required
def delete_all():
    service.delete_all_viewed_and_liked(g.user.username)
    html = render_template("partials/viewed_table.html", quotes_with_like=[])
    html += render_template(
        "partials/toast.html",
        message="All viewed and liked quotes deleted. Next quote starts from the beginning.",
        toast_type="success",
    )
    return Response(html, status=200)
