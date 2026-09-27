"""Cached boto3 client/resource factories.

Lambda execution environments are reused across warm invocations, and boto3
clients are safe (and comparatively expensive) to share across requests
within one environment - so these are created once per process via
lru_cache rather than once per request.
"""

import os
from functools import lru_cache

import boto3

_REGION = os.environ.get("AWS_REGION", "eu-central-1")


@lru_cache(maxsize=1)
def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=_REGION)


@lru_cache(maxsize=1)
def dynamodb_client():
    """A plain low-level client, distinct from dynamodb_resource().meta.client.

    The resource's client carries boto3's high-level Decimal/AttributeValue
    auto-transform (meant for get_item/put_item/query/... called through
    the resource), which double-processes the already-serialized
    AttributeValue dicts app/dynamo/transact.py builds for
    TransactWriteItems and fails. Cross-table transactional writes go
    through this client instead.
    """
    return boto3.client("dynamodb", region_name=_REGION)


@lru_cache(maxsize=1)
def cognito_idp_client():
    return boto3.client("cognito-idp", region_name=_REGION)


def region() -> str:
    return _REGION
