from flask import Blueprint, Response, g, render_template, request

from app.auth.decorators import login_required
from app.quotes import service

quotes_bp = Blueprint("quotes", __name__, url_prefix="/quote")


def _parse_excluded_ids() -> set[int]:
    raw = request.form.get("excluded_ids", "") or ""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def _render_quote_card(quote, status: int = 200) -> Response:
    liked = False
    if quote is not None and g.get("user") is not None:
        liked = service.is_liked(g.user.username, quote.quote_id)

    progress = None
    if g.get("user") is not None:
        progress = service.get_user_progress(g.user.username)
    last_quote_id = progress.last_quote_id if progress else 0

    display = render_template("partials/quote_display.html", quote=quote)
    actions = render_template(
        "partials/quote_actions.html",
        quote=quote,
        liked=liked,
        last_quote_id=last_quote_id,
        oob=True,
    )
    return Response(display + actions, status=status)


@quotes_bp.route("/new", methods=["POST"])
def new_quote():
    if g.get("user") is not None:
        quote = service.get_next_quote_for_user(g.user.username)
    else:
        excluded = _parse_excluded_ids()
        quote = service.get_random_quote(excluded)

    if quote is None:
        return _render_quote_card(None, status=404)
    return _render_quote_card(quote)


@quotes_bp.route("/<int:quote_id>", methods=["GET"])
@login_required
def get_quote(quote_id: int):
    progress = service.get_user_progress(g.user.username)
    last_quote_id = progress.last_quote_id if progress else 0
    if quote_id < 1 or quote_id > max(last_quote_id, 1):
        quote_id = max(min(quote_id, last_quote_id), 1)

    quote = service.get_quote_by_id(quote_id)
    if quote is None:
        return _render_quote_card(None, status=404)
    return _render_quote_card(quote)


def _render_favourites_strip_oob() -> str:
    quotes = []
    if g.get("user") is not None:
        quotes = service.get_liked_quotes_for_user(g.user.username)
    return render_template("partials/favourites_strip.html", quotes=quotes, oob=True)


@quotes_bp.route("/<int:quote_id>/like", methods=["POST"])
@login_required
def like_quote(quote_id: int):
    quote = service.like_quote(g.user.username, quote_id)
    if quote is None:
        return _render_quote_card(None, status=404)
    card = _render_quote_card(quote)
    return Response(card.get_data(as_text=True) + _render_favourites_strip_oob(), status=200)


@quotes_bp.route("/<int:quote_id>/unlike", methods=["DELETE"])
@login_required
def unlike_quote(quote_id: int):
    quote = service.unlike_quote(g.user.username, quote_id)
    if quote is None:
        return _render_quote_card(None, status=404)
    card = _render_quote_card(quote)
    return Response(card.get_data(as_text=True) + _render_favourites_strip_oob(), status=200)
