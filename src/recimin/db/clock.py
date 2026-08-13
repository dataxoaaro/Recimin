"""Timestamps.

One helper so every row uses the same format, and so tests can freeze it.
"""

from datetime import UTC, datetime


def now() -> str:
    """Current UTC time as an ISO-8601 string with a Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
