"""Plain dataclasses that replace the old SQLAlchemy models.

Field names are kept identical to the source app's SQLAlchemy models
(``quote.quote_id``, ``quote.quote_text``, ``user.username`` ...) so that
every Jinja template copied verbatim from quote-k8s-python keeps working
without edits - only the object construction changed (DynamoDB items /
Cognito API responses instead of ORM rows).
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Quote:
    quote_id: int
    quote_text: str
    author: str = "Unknown"
    like_count: int = 0
    created_at: datetime | None = None
    source: str = "Local"


@dataclass
class UserProgress:
    username: str
    last_quote_id: int = 0
    updated_at: datetime | None = None


@dataclass
class CurrentUser:
    """The authenticated principal for the current request, built from
    verified Cognito ID-token claims (see app/__init__.py before_request)."""

    username: str
    email: str
    sub: str


@dataclass
class UserSummary:
    """Assembled at request time from Cognito, replacing the old User+UserRole tables."""

    username: str
    email: str
    roles: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
