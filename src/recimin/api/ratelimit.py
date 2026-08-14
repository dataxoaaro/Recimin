"""Rate limiting backed by SQLite.

Arboretium uses Cloudflare KV for this; we have one node and a database, so a
table is simpler and survives restarts. Counters are bucketed by a fixed window,
which is coarse but adequate for slowing password guessing at household scale.

Only failures are counted. An earlier version incremented before validating
anything, so a legitimate person near the cap was locked out by their own
successful attempts — and because the check ran before the password comparison,
the response said "too many attempts" whether or not the password was right,
which is indistinguishable from a wrong password at the UI.

A success clears the bucket outright: proving you know the credential is the
strongest possible evidence you are not the guesser it exists to slow down.
"""

import sqlite3
import time
from dataclasses import dataclass

LOGIN_PER_EMAIL = (5, 15 * 60)
LOGIN_PER_IP = (20, 15 * 60)
REGISTER_PER_IP = (10, 60 * 60)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limits (
  bucket     TEXT NOT NULL,
  window_start INTEGER NOT NULL,
  hits       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket, window_start)
)
"""


@dataclass(frozen=True, slots=True)
class Decision:
    """Whether an attempt may proceed, and when the caller may retry.

    `retry_after_seconds` is time remaining in the current fixed window, so it
    counts down to the next boundary rather than starting a fresh interval from
    the last attempt. It is 0 whenever `allowed` is true.
    """

    allowed: bool
    retry_after_seconds: int = 0


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create the counter table if it does not exist.

    Kept out of the migrations because it is throwaway operational state, not
    part of the data model; dropping it costs nothing. Run once at app
    startup, not per request.
    """
    conn.execute(_SCHEMA)


def _window_start(timestamp: int, window: int) -> int:
    return timestamp - (timestamp % window)


def check(
    conn: sqlite3.Connection, bucket: str, limit: tuple[int, int], *, now: float | None = None
) -> Decision:
    """Report whether the bucket is under its limit, without recording anything.

    Read-only by design: an attempt that is rejected here must not extend its
    own lockout, and an attempt that succeeds must not be charged for existing.
    """
    max_hits, window = limit
    timestamp = int(now if now is not None else time.time())
    window_start = _window_start(timestamp, window)

    row = conn.execute(
        "SELECT hits FROM rate_limits WHERE bucket = ? AND window_start = ?",
        (bucket, window_start),
    ).fetchone()
    hits = int(row["hits"]) if row else 0

    if hits < max_hits:
        return Decision(allowed=True)
    return Decision(allowed=False, retry_after_seconds=window_start + window - timestamp)


def record_failure(
    conn: sqlite3.Connection, bucket: str, limit: tuple[int, int], *, now: float | None = None
) -> None:
    """Charge the bucket for an attempt that genuinely failed."""
    _, window = limit
    timestamp = int(now if now is not None else time.time())

    # Housekeeping piggybacked on the table's only write path: without it,
    # stale window rows accumulated for the life of the database.
    purge_expired(conn, now=timestamp)

    conn.execute(
        "INSERT INTO rate_limits (bucket, window_start, hits) VALUES (?, ?, 1)"
        " ON CONFLICT(bucket, window_start) DO UPDATE SET hits = hits + 1",
        (bucket, _window_start(timestamp, window)),
    )


def clear(conn: sqlite3.Connection, bucket: str) -> None:
    """Forget a bucket's failures, after an attempt that succeeded."""
    conn.execute("DELETE FROM rate_limits WHERE bucket = ?", (bucket,))


def describe_wait(seconds: int) -> str:
    """A human retry hint. 'Try again later' tells the user nothing actionable."""
    if seconds <= 90:
        whole = max(seconds, 1)
        return "1 second" if whole == 1 else f"{whole} seconds"
    minutes = round(seconds / 60)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def purge_expired(
    conn: sqlite3.Connection,
    *,
    older_than_seconds: int = 24 * 60 * 60,
    now: float | None = None,
) -> int:
    """Drop stale counter rows. Returns how many went."""
    cutoff = int(now if now is not None else time.time()) - older_than_seconds
    cursor = conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
    return cursor.rowcount
