from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naive datetimes as UTC so comparisons are safe."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
