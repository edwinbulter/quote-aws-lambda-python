# DynamoDB schema

Three tables (mirrors the shape used by quote-lambda-tf-backend's Java
implementation), all `PAY_PER_REQUEST`, point-in-time recovery and
server-side encryption enabled. See `infrastructure/dynamodb.tf` for the
Terraform and `app/dynamo/*_repo.py` for the access code.

## `quotes`

PK `id` (N).

| Attribute | Type | Notes |
|---|---|---|
| `id` | N | quote id, or `0` for the reserved counter item |
| `quoteText` | S | |
| `author` | S | |
| `likeCount` | N | denormalized, kept consistent via `TransactWriteItems` (see below) |
| `source` | S | `"Local"` \| `"ZenQuotes"` |
| `createdAt` | N | epoch-ms |
| `counterValue` | N | **only** on the `id=0` sentinel item |

GSI `AuthorIndex`: hash `author`, projection `ALL` (sparse - the counter
sentinel carries no `author` attribute so it never appears in it).

### The id=0 counter sentinel

DynamoDB has no autoincrement. Both SQLite's autoincrement and the Java
reference's `Scan`-for-`MAX(id)` approach are replaced by one reserved
item, `{id: 0, counterValue: N}`:

- **Next id(s):** `UpdateItem(Key={id:0}, ADD counterValue :n)` -
  DynamoDB initializes `counterValue` to 0 before adding if the item
  doesn't exist yet, so no pre-seeding is required. The returned new
  value **is** the freshly reserved id (or, for a batch of `n`, the ids
  are `new_value-n+1 .. new_value`). See `quotes_repo.reserve_ids()`.
- **`max_id()`:** a single `GetItem(id=0)` - no scan.
- Must be excluded from admin listing/search scans (filtered via
  `attribute_exists(quoteText)`, which the sentinel never has).

## `user_likes`

PK `username` (S), SK `quoteId` (N).

| Attribute | Type |
|---|---|
| `order` | N - drag-reorder position among a user's favourites |
| `likedAt` | N - epoch-ms |

GSI `QuoteIdIndex`: hash `quoteId`, range `likedAt`, projection `ALL`
(kept for parity with the reference; not exercised by current app logic).

Uniqueness of (username, quoteId) is structural (PK+SK); "like" is
idempotent via `ConditionExpression: attribute_not_exists(quoteId)`.

## `user_progress`

PK `username` (S).

| Attribute | Type |
|---|---|
| `lastQuoteId` | N |
| `updatedAt` | N - epoch-ms |

GSI `LastQuoteIdIndex`: hash `lastQuoteId`, range `updatedAt` (parity with
the reference, not currently queried by the app).

## No `users`/`user_roles` tables

Cognito (User Pool + `USER`/`ADMIN` groups) is the identity/roles store
now - see `auth-flow.md`. The admin user roster is assembled at request
time from Cognito API calls, not read from DynamoDB.

## Keeping `likeCount` consistent: `TransactWriteItems`

Like/unlike touch two tables atomically (`app/dynamo/user_likes_repo.py`,
via `app/dynamo/transact.py`):

- **Like:** `Put` the `user_likes` item (`ConditionExpression:
  attribute_not_exists(quoteId)`) + `Update quotes SET likeCount =
  likeCount + :1` (`ConditionExpression: attribute_exists(id)`), in one
  `TransactWriteItems` call. A cancelled transaction (concurrent duplicate
  like) is treated as an idempotent no-op, matching the source app.
- **Unlike:** the mirror image, decrementing with `ConditionExpression:
  likeCount > :0` so the count never goes negative (clamped at 0, matching
  the source's `max(count-1, 0)`); a cancellation here falls back to a
  plain conditional delete so the like is still removed even if the
  counter was already at 0.
- **Reorder** (`swap_order`): two conditional `Update`s (optimistic
  concurrency via `order = :expected`) in one transaction - DynamoDB has
  no "swap two rows" primitive.

`transact_write_items` is called through a **plain low-level** `boto3`
client (`aws_clients.dynamodb_client()`), not `dynamodb_resource().meta.client`
- the resource's client carries an automatic Python-type→AttributeValue
transform meant for `get_item`/`put_item`/etc. that double-processes the
already-serialized items this module builds and fails. See
`app/dynamo/transact.py` for the manual `TypeSerializer`-based
serialization this uses instead.

## Why 3 tables instead of a single-table design

Considered and rejected: this app's access patterns are simple
single-entity point reads/writes (get quote by id, get a user's likes,
get/set a user's progress), and the one cross-entity write (like/unlike)
is already handled cleanly by `TransactWriteItems` across tables (which
supports up to 100 items across multiple tables in one region - multi-table
doesn't block atomicity). Three small tables keep IAM policy, Terraform,
and the mental model simple; single-table design's main payoff (fewer
round trips for hierarchical queries) doesn't apply here.

## Admin listing has no `ORDER BY`/`LIKE`

The admin quotes table's free-text search, sort-by-column and pagination
(`app/admin/service.py`) is implemented as: `quotes_repo.scan_all()`
(paginating internally via `LastEvaluatedKey`) → filter/sort/slice in
Python. This is an accepted `O(n)` full-table-scan-per-request tradeoff at
this app's expected scale (hundreds to low thousands of quotes) - there is
no DynamoDB-native equivalent to a SQL `ILIKE`/`ORDER BY` without adding a
search service, which isn't justified here.
