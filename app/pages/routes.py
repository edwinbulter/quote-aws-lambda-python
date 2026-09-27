from flask import Blueprint, g, render_template, request

from app.admin import service as admin_service
from app.auth.decorators import login_required, roles_required
from app.quotes import service as quote_service

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/", methods=["GET"])
def index():
    if g.get("user") is not None:
        quote = quote_service.get_next_quote_for_user(g.user.username)
        progress = quote_service.get_user_progress(g.user.username)
        last_quote_id = progress.last_quote_id if progress else 0
        liked = quote_service.is_liked(g.user.username, quote.quote_id) if quote else False
        favourites = quote_service.get_liked_quotes_for_user(g.user.username)
    else:
        quote = quote_service.get_random_quote(set())
        last_quote_id = 0
        liked = False
        favourites = []

    return render_template(
        "pages/quote_view.html",
        quote=quote,
        liked=liked,
        last_quote_id=last_quote_id,
        favourites=favourites,
    )


@pages_bp.route("/login", methods=["GET"])
def login():
    mode = request.args.get("mode", "login")
    if mode not in ("login", "register"):
        mode = "login"
    return render_template("pages/auth_form.html", mode=mode, error=None, values={})


@pages_bp.route("/profile", methods=["GET"])
@login_required
def profile():
    roles = sorted(g.roles)
    return render_template("pages/profile.html", user=g.user, roles=roles)


@pages_bp.route("/manage", methods=["GET"])
@login_required
def management_menu():
    return render_template("pages/management_menu.html")


@pages_bp.route("/manage/favourites", methods=["GET"])
@login_required
def manage_favourites():
    quotes = quote_service.get_liked_quotes_for_user(g.user.username)
    return render_template("pages/manage_favourites.html", quotes=quotes)


@pages_bp.route("/manage/viewed", methods=["GET"])
@login_required
def manage_viewed():
    quotes = quote_service.get_viewed_quotes_for_user(g.user.username)
    liked_ids = {q.quote_id for q in quote_service.get_liked_quotes_for_user(g.user.username)}
    quotes_with_like = [(q, q.quote_id in liked_ids) for q in reversed(quotes)]
    return render_template("pages/manage_viewed.html", quotes_with_like=quotes_with_like)


@pages_bp.route("/manage/users", methods=["GET"])
@roles_required("ADMIN")
def manage_users():
    users = admin_service.list_users()
    return render_template("pages/user_management.html", users=users, current_username=g.user.username)


@pages_bp.route("/manage/quotes", methods=["GET"])
@roles_required("ADMIN")
def manage_quotes():
    result = admin_service.get_quotes(1, 50, None, None, "id", "asc")
    return render_template(
        "pages/quote_management.html",
        **result,
        quote_text="",
        author="",
        total_likes=admin_service.get_total_likes(),
    )
