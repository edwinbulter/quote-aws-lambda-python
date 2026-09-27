"""Repository for the `user_progress` DynamoDB table.

Schema: PK `username` (S). Attrs: lastQuoteId (N), updatedAt (N).
"""

from flask import current_app

from app.dynamo import ms_to_datetime, now_ms
from app.models import UserProgress


def _table():
    from app.aws_clients import dynamodb_resource

    return dynamodb_resource().Table(current_app.config["USER_PROGRESS_TABLE"])


def get(username: str) -> UserProgress | None:
    resp = _table().get_item(Key={"username": username})
    item = resp.get("Item")
    if not item:
        return None
    return UserProgress(
        username=username,
        last_quote_id=int(item.get("lastQuoteId", 0)),
        updated_at=ms_to_datetime(int(item["updatedAt"])) if "updatedAt" in item else None,
    )


def set_last_quote_id(username: str, last_quote_id: int) -> None:
    _table().put_item(Item={"username": username, "lastQuoteId": last_quote_id, "updatedAt": now_ms()})


def delete(username: str) -> None:
    _table().delete_item(Key={"username": username})
