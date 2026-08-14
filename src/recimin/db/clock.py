"""Timestamps.

One helper so every row uses the same format, and so tests can freeze it.
"""

from datetime import UTC, datetime, timedelta

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now() -> str:
    """Current UTC time as an ISO-8601 string with a Z suffix."""
    return datetime.now(UTC).strftime(_FORMAT)


def days_ago(days: int) -> str:
    """A timestamp `days` before now, in the same format and therefore
    comparable to stored timestamps as a plain string."""
    return (datetime.now(UTC) - timedelta(days=days)).strftime(_FORMAT)
