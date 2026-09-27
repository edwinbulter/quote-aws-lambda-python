import math

from app.auth import cognito_client
from app.dynamo import quotes_repo, user_likes_repo
from app.models import Quote, UserSummary
from app.services import zen_quotes

SORTABLE_COLUMNS = {
    "id": lambda q: q.quote_id,
    "quotetext": lambda q: q.quote_text.lower(),
    "author": lambda q: q.author.lower(),
    "likes": lambda q: q.like_count,
}


def list_users() -> list[UserSummary]:
    return cognito_client.list_users()


def grant_role(username: str, role: str, granted_by: str) -> bool:
    return cognito_client.add_user_to_group(username, role.upper())


def revoke_role(username: str, role: str) -> bool:
    return cognito_client.remove_user_from_group(username, role.upper())


def get_quotes(
    page: int,
    page_size: int,
    quote_text: str | None,
    author: str | None,
    sort_by: str,
    sort_order: str,
) -> dict:
    quotes: list[Quote] = quotes_repo.scan_all()

    if quote_text:
        needle = quote_text.lower()
        quotes = [q for q in quotes if needle in q.quote_text.lower()]
    if author:
        needle = author.lower()
        quotes = [q for q in quotes if needle in q.author.lower()]

    sort_by = (sort_by or "id").lower()
    key_fn = SORTABLE_COLUMNS.get(sort_by, SORTABLE_COLUMNS["id"])

    if sort_by == "likes":
        # Likes only supports descending sort, matching the reference UI.
        quotes.sort(key=key_fn, reverse=True)
        sort_order = "desc"
    else:
        sort_order = (sort_order or "asc").lower()
        quotes.sort(key=key_fn, reverse=(sort_order == "desc"))

    total_count = len(quotes)
    total_pages = max(math.ceil(total_count / page_size), 1) if page_size else 1
    page = max(min(page, total_pages), 1)

    start = (page - 1) * page_size
    page_quotes = quotes[start : start + page_size]

    return {
        "quotes": page_quotes,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


def fetch_and_add_new_quotes() -> int:
    fetched = zen_quotes.fetch_many()
    if not fetched:
        return 0

    existing = {(q.quote_text.lower(), (q.author or "").lower()) for q in quotes_repo.scan_all()}
    entries: list[tuple[str, str]] = []
    for item in fetched:
        text = item.get("q")
        author = item.get("a") or "Unknown"
        if not text:
            continue
        key = (text.lower(), author.lower())
        if key in existing:
            continue
        entries.append((text, author))
        existing.add(key)

    if not entries:
        return 0
    quotes_repo.batch_put_new(entries, source="ZenQuotes")
    return len(entries)


def get_total_likes() -> int:
    return user_likes_repo.count_all()


def get_total_quotes() -> int:
    return len(quotes_repo.scan_all())
