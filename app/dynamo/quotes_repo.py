"""Repository for the `quotes` DynamoDB table.

Schema: PK `id` (N). Attrs: quoteText (S), author (S), likeCount (N),
source (S), createdAt (N, epoch-ms).

Item `{id: 0}` is a reserved counter sentinel (attribute `counterValue`,
N) used to generate dense sequential quote ids without a table scan -
see next_id()/reserve_ids()/max_id(). It is filtered out of scan_all()
via a FilterExpression on `quoteText` (the sentinel never carries one).
"""

from boto3.dynamodb.conditions import Attr
from flask import current_app

from app.dynamo import now_ms
from app.models import Quote

COUNTER_ID = 0


def _table():
    from app.aws_clients import dynamodb_resource

    return dynamodb_resource().Table(current_app.config["QUOTES_TABLE"])


def _to_quote(item: dict) -> Quote:
    from app.dynamo import ms_to_datetime

    return Quote(
        quote_id=int(item["id"]),
        quote_text=item.get("quoteText", ""),
        author=item.get("author", "Unknown"),
        like_count=int(item.get("likeCount", 0)),
        created_at=ms_to_datetime(int(item["createdAt"])) if "createdAt" in item else None,
        source=item.get("source", "Local"),
    )


def get_by_id(quote_id: int) -> Quote | None:
    if quote_id == COUNTER_ID:
        return None
    resp = _table().get_item(Key={"id": quote_id})
    item = resp.get("Item")
    return _to_quote(item) if item else None


def batch_get(quote_ids: list[int]) -> dict[int, Quote]:
    ids = [qid for qid in set(quote_ids) if qid != COUNTER_ID]
    if not ids:
        return {}
    table_name = current_app.config["QUOTES_TABLE"]
    result: dict[int, Quote] = {}
    from app.aws_clients import dynamodb_resource

    resource = dynamodb_resource()
    # BatchGetItem allows at most 100 keys per request.
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        resp = resource.batch_get_item(
            RequestItems={table_name: {"Keys": [{"id": qid} for qid in chunk]}}
        )
        for item in resp.get("Responses", {}).get(table_name, []):
            quote = _to_quote(item)
            result[quote.quote_id] = quote
    return result


def scan_all() -> list[Quote]:
    """Full scan, excluding the counter sentinel. Paginates internally.

    Accepted O(N) cost for admin listing/search/sort and fetch-zen dedup
    at this app's expected quote volume - see plan doc for rationale.
    """
    table = _table()
    quotes: list[Quote] = []
    kwargs = {"FilterExpression": Attr("quoteText").exists()}
    while True:
        resp = table.scan(**kwargs)
        quotes.extend(_to_quote(item) for item in resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return quotes


def max_id() -> int:
    resp = _table().get_item(Key={"id": COUNTER_ID})
    item = resp.get("Item")
    if not item:
        return 0
    return int(item.get("counterValue", 0))


def reserve_ids(count: int) -> list[int]:
    """Atomically reserve `count` new sequential ids, returning them in order."""
    if count <= 0:
        return []
    resp = _table().update_item(
        Key={"id": COUNTER_ID},
        UpdateExpression="ADD counterValue :n",
        ExpressionAttributeValues={":n": count},
        ReturnValues="UPDATED_NEW",
    )
    new_value = int(resp["Attributes"]["counterValue"])
    first_id = new_value - count + 1
    return list(range(first_id, new_value + 1))


def next_id() -> int:
    return reserve_ids(1)[0]


def put_new(quote_text: str, author: str, source: str = "Local") -> Quote:
    quote_id = next_id()
    quote = Quote(quote_id=quote_id, quote_text=quote_text, author=author or "Unknown", like_count=0, source=source)
    _table().put_item(
        Item={
            "id": quote.quote_id,
            "quoteText": quote.quote_text,
            "author": quote.author,
            "likeCount": 0,
            "source": quote.source,
            "createdAt": now_ms(),
        }
    )
    return quote


def batch_put_new(entries: list[tuple[str, str]], source: str = "ZenQuotes") -> list[Quote]:
    """Reserve len(entries) ids in one atomic increment, then BatchWriteItem the puts."""
    if not entries:
        return []
    ids = reserve_ids(len(entries))
    created_at = now_ms()
    quotes = [
        Quote(quote_id=qid, quote_text=text, author=author or "Unknown", like_count=0, source=source)
        for qid, (text, author) in zip(ids, entries, strict=True)
    ]

    from app.aws_clients import dynamodb_resource

    table_name = current_app.config["QUOTES_TABLE"]
    resource = dynamodb_resource()
    # BatchWriteItem allows at most 25 items per request.
    for i in range(0, len(quotes), 25):
        chunk = quotes[i : i + 25]
        resource.batch_write_item(
            RequestItems={
                table_name: [
                    {
                        "PutRequest": {
                            "Item": {
                                "id": q.quote_id,
                                "quoteText": q.quote_text,
                                "author": q.author,
                                "likeCount": 0,
                                "source": q.source,
                                "createdAt": created_at,
                            }
                        }
                    }
                    for q in chunk
                ]
            }
        )
    return quotes


def like_count_transact_update(quote_id: int, delta: int, require_positive: bool = False) -> dict:
    """Build a TransactWriteItems `Update` spec that adjusts likeCount by delta."""
    condition = "attribute_exists(id)"
    values = {":delta": delta}
    if require_positive:
        condition += " AND likeCount > :zero"
        values[":zero"] = 0
    return {
        "Update": {
            "TableName": current_app.config["QUOTES_TABLE"],
            "Key": {"id": quote_id},
            "UpdateExpression": "SET likeCount = likeCount + :delta",
            "ConditionExpression": condition,
            "ExpressionAttributeValues": values,
        }
    }
