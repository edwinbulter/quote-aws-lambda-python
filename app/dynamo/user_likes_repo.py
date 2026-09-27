"""Repository for the `user_likes` DynamoDB table.

Schema: PK `username` (S), SK `quoteId` (N). Attrs: order (N), likedAt (N).

Like/unlike touch this table AND the quotes table's denormalized
likeCount atomically via TransactWriteItems (see app/dynamo/transact.py
and quotes_repo.like_count_transact_update).
"""

from flask import current_app

from app.dynamo import now_ms
from app.dynamo.quotes_repo import like_count_transact_update
from app.dynamo.transact import TransactionCancelled, transact_write


def _table():
    from app.aws_clients import dynamodb_resource

    return dynamodb_resource().Table(current_app.config["USER_LIKES_TABLE"])


def get(username: str, quote_id: int) -> dict | None:
    resp = _table().get_item(Key={"username": username, "quoteId": quote_id})
    return resp.get("Item")


def query_by_username(username: str) -> list[dict]:
    items: list[dict] = []
    kwargs = {"KeyConditionExpression": "username = :u", "ExpressionAttributeValues": {":u": username}}
    table = _table()
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def like(username: str, quote_id: int) -> bool:
    """Idempotent like. Returns True if newly liked, False if already liked."""
    if get(username, quote_id) is not None:
        return False

    existing = query_by_username(username)
    max_order = max((int(item.get("order", 0)) for item in existing), default=0)

    table_name = current_app.config["USER_LIKES_TABLE"]
    put_spec = {
        "Put": {
            "TableName": table_name,
            "Item": {"username": username, "quoteId": quote_id, "order": max_order + 1, "likedAt": now_ms()},
            "ConditionExpression": "attribute_not_exists(quoteId)",
        }
    }
    try:
        transact_write([put_spec, like_count_transact_update(quote_id, +1)])
    except TransactionCancelled:
        # Concurrent duplicate like (or the quote vanished) - idempotent no-op.
        return False
    return True


def unlike(username: str, quote_id: int) -> bool:
    """Idempotent unlike. Returns True if removed, False if it wasn't liked."""
    if get(username, quote_id) is None:
        return False

    table_name = current_app.config["USER_LIKES_TABLE"]
    delete_spec = {
        "Delete": {
            "TableName": table_name,
            "Key": {"username": username, "quoteId": quote_id},
            "ConditionExpression": "attribute_exists(quoteId)",
        }
    }
    try:
        transact_write([delete_spec, like_count_transact_update(quote_id, -1, require_positive=True)])
    except TransactionCancelled:
        # Either already removed by a concurrent request, or likeCount was
        # already at 0 (clamped, matching the source's max(count-1, 0)) -
        # retry the delete alone so the like is still removed.
        try:
            _table().delete_item(
                Key={"username": username, "quoteId": quote_id},
                ConditionExpression="attribute_exists(quoteId)",
            )
        except Exception:
            return False
    return True


def swap_order(username: str, quote_id_a: int, order_a: int, quote_id_b: int, order_b: int) -> bool:
    """Swap the `order` attribute of two of a user's likes (adjacent-swap reorder)."""
    table_name = current_app.config["USER_LIKES_TABLE"]

    def _update(quote_id: int, new_order: int, expected_order: int) -> dict:
        return {
            "Update": {
                "TableName": table_name,
                "Key": {"username": username, "quoteId": quote_id},
                "UpdateExpression": "SET #o = :new_order",
                "ConditionExpression": "#o = :expected_order",
                "ExpressionAttributeNames": {"#o": "order"},
                "ExpressionAttributeValues": {":new_order": new_order, ":expected_order": expected_order},
            }
        }

    try:
        transact_write(
            [_update(quote_id_a, order_b, order_a), _update(quote_id_b, order_a, order_b)]
        )
    except TransactionCancelled:
        return False
    return True


def count_all() -> int:
    """Total number of likes across all users (for the admin quotes-table
    stat). A full-table Scan is the only option DynamoDB offers for a
    global count with no ORM aggregate - accepted at this app's scale."""
    table = _table()
    total = 0
    kwargs = {"Select": "COUNT"}
    while True:
        resp = table.scan(**kwargs)
        total += resp.get("Count", 0)
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return total


def delete_all_for_user(username: str) -> None:
    """Unlike every quote a user has liked, correctly decrementing likeCount
    for each (the SQLAlchemy source bulk-deleted UserLike rows without
    touching Quote.like_count - a latent bug; this deliberately fixes it)."""
    for item in query_by_username(username):
        unlike(username, int(item["quoteId"]))
