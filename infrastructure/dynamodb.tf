# Three tables mirroring the shape used by the quote-lambda-tf-backend
# reference (Java) implementation: quotes / user_likes / user_progress.
# See doc/dynamodb-schema.md for the full item-shape writeup, including
# the `quotes` table's reserved id=0 counter-sentinel item used to
# generate sequential quote ids without a table scan.

resource "aws_dynamodb_table" "quotes" {
  name         = var.quotes_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "N"
  }

  attribute {
    name = "author"
    type = "S"
  }

  global_secondary_index {
    name            = "AuthorIndex"
    hash_key        = "author"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "user_likes" {
  name         = var.user_likes_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "username"
  range_key    = "quoteId"

  attribute {
    name = "username"
    type = "S"
  }

  attribute {
    name = "quoteId"
    type = "N"
  }

  attribute {
    name = "likedAt"
    type = "N"
  }

  global_secondary_index {
    name            = "QuoteIdIndex"
    hash_key        = "quoteId"
    range_key       = "likedAt"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "user_progress" {
  name         = var.user_progress_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "username"

  attribute {
    name = "username"
    type = "S"
  }

  attribute {
    name = "lastQuoteId"
    type = "N"
  }

  attribute {
    name = "updatedAt"
    type = "N"
  }

  global_secondary_index {
    name            = "LastQuoteIdIndex"
    hash_key        = "lastQuoteId"
    range_key       = "updatedAt"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}
