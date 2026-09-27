"""Serialization helper for cross-table DynamoDB TransactWriteItems.

The high-level "resource" Table API (which auto-serializes plain Python
values) has no transact_write_items method - that only exists on the
low-level client, which expects DynamoDB wire-format AttributeValue dicts.
Repos build transact item specs with plain Python values (int/str/etc,
matching put_item/update_item elsewhere in this codebase); this module
serializes them just before sending.
"""

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

_serializer = TypeSerializer()


def _serialize_map(d: dict) -> dict:
    return {k: _serializer.serialize(v) for k, v in d.items()}


def _serialize_spec(spec: dict) -> dict:
    op, body = next(iter(spec.items()))
    body = dict(body)
    for key in ("Key", "Item", "ExpressionAttributeValues"):
        if key in body:
            body[key] = _serialize_map(body[key])
    return {op: body}


class TransactionCancelled(Exception):
    """Raised when a TransactWriteItems call fails a ConditionExpression check."""


def transact_write(specs: list[dict]) -> None:
    from app.aws_clients import dynamodb_client

    client = dynamodb_client()
    try:
        client.transact_write_items(TransactItems=[_serialize_spec(s) for s in specs])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
            raise TransactionCancelled(str(exc)) from exc
        raise
