import logging
import random

from app.dynamo import quotes_repo, user_likes_repo, user_progress_repo
from app.models import Quote, UserProgress
from app.services import zen_quotes

logger = logging.getLogger(__name__)

MIN_POOL_SIZE = 5


def _fetch_more_quotes_if_needed() -> int:
    """Pull a batch from ZenQuotes and append any not already present,
    deduped by (text.lower(), author.lower()). Never raises - degrades to
    "added nothing" on failure.

    Note: the source app dedups this call site by exact quote_text only,
    while its admin "fetch from ZEN" route (see app/admin/service.py)
    dedups by the normalized (text.lower(), author.lower()) tuple - an
    inconsistency between the two call sites. This port deliberately
    normalizes both to the same key.
    """
    fetched = zen_quotes.fetch_many()
    if not fetched:
        logger.info("ZenQuotes returned no quotes; continuing with existing pool")
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


def get_random_quote(exclude_ids: set[int]) -> Quote | None:
    max_id = quotes_repo.max_id()
    if max_id < MIN_POOL_SIZE or max_id <= len(exclude_ids):
        _fetch_more_quotes_if_needed()
        max_id = quotes_repo.max_id()

    if max_id == 0:
        return None

    max_attempts = min(100, max_id)
    attempted: set[int] = set()
    for _ in range(max_attempts):
        candidate = random.randint(1, max_id)
        if candidate in exclude_ids or candidate in attempted:
            continue
        attempted.add(candidate)
        quote = quotes_repo.get_by_id(candidate)
        if quote is not None:
            return quote

    candidates = [q for q in quotes_repo.scan_all() if q.quote_id not in exclude_ids]
    if not candidates:
        return None
    return random.choice(candidates)


def _find_next_available_quote(start_id: int, max_id: int) -> Quote | None:
    for quote_id in range(start_id, max_id + 1):
        quote = quotes_repo.get_by_id(quote_id)
        if quote is not None:
            return quote
    return None


def get_next_quote_for_user(username: str) -> Quote | None:
    progress = user_progress_repo.get(username)
    next_id = (progress.last_quote_id + 1) if progress else 1

    max_id = quotes_repo.max_id()
    if next_id > max_id:
        _fetch_more_quotes_if_needed()
        max_id = quotes_repo.max_id()

    quote = quotes_repo.get_by_id(next_id)
    if quote is None:
        quote = _find_next_available_quote(next_id, max_id)
    if quote is None:
        return None

    user_progress_repo.set_last_quote_id(username, quote.quote_id)
    return quote


def get_quote_by_id(quote_id: int) -> Quote | None:
    return quotes_repo.get_by_id(quote_id)


def get_viewed_quotes_for_user(username: str) -> list[Quote]:
    progress = user_progress_repo.get(username)
    if progress is None or progress.last_quote_id <= 0:
        return []
    ids = list(range(1, progress.last_quote_id + 1))
    quotes_by_id = quotes_repo.batch_get(ids)
    return [quotes_by_id[qid] for qid in ids if qid in quotes_by_id]


def get_user_progress(username: str) -> UserProgress | None:
    return user_progress_repo.get(username)


def like_quote(username: str, quote_id: int) -> Quote | None:
    if quotes_repo.get_by_id(quote_id) is None:
        return None
    user_likes_repo.like(username, quote_id)
    return quotes_repo.get_by_id(quote_id)


def unlike_quote(username: str, quote_id: int) -> Quote | None:
    if quotes_repo.get_by_id(quote_id) is None:
        return None
    user_likes_repo.unlike(username, quote_id)
    return quotes_repo.get_by_id(quote_id)


def get_liked_quotes_for_user(username: str) -> list[Quote]:
    likes = sorted(user_likes_repo.query_by_username(username), key=lambda item: int(item.get("order", 0)))
    ids = [int(item["quoteId"]) for item in likes]
    quotes_by_id = quotes_repo.batch_get(ids)
    return [quotes_by_id[qid] for qid in ids if qid in quotes_by_id]


def is_liked(username: str, quote_id: int) -> bool:
    return user_likes_repo.get(username, quote_id) is not None


def move_favourite(username: str, quote_id: int, direction: str) -> bool:
    """Swap the order of a liked quote with its immediate neighbor."""
    likes = sorted(user_likes_repo.query_by_username(username), key=lambda item: int(item.get("order", 0)))
    index = next((i for i, item in enumerate(likes) if int(item["quoteId"]) == quote_id), None)
    if index is None:
        return False

    if direction == "up" and index > 0:
        neighbor_index = index - 1
    elif direction == "down" and index < len(likes) - 1:
        neighbor_index = index + 1
    else:
        return False

    current = likes[index]
    neighbor = likes[neighbor_index]
    return user_likes_repo.swap_order(
        username,
        int(current["quoteId"]),
        int(current.get("order", 0)),
        int(neighbor["quoteId"]),
        int(neighbor.get("order", 0)),
    )


def delete_all_viewed_and_liked(username: str) -> None:
    user_likes_repo.delete_all_for_user(username)
    user_progress_repo.set_last_quote_id(username, 0)
