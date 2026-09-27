from datetime import UTC, datetime


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def ms_to_datetime(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC).replace(tzinfo=None)
