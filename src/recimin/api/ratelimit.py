"""Rate limiting backed by SQLite.

Arboretium uses Cloudflare KV for this; we have one node and a database, so a
table is simpler and survives restarts. Counters are bucketed by a fixed window,
which is coarse but adequate for slowing password guessing at household scale.
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
class Limit:
    """A maximum number of hits within a rolling window of whole seconds."""

    max_hits: int
    window_seconds: int


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create the counter table if it does not exist.

    Kept out of the migrations because it is throwaway operational state, not
    part of the data model; dropping it costs nothing.
    """
    conn.execute(_SCHEMA)


def check_and_increment(
    conn: sqlite3.Connection, bucket: str, limit: tuple[int, int], *, now: float | None = None
) -> bool:
    """Record a hit and report whether the caller is still under the limit.

    Returns False once the bucket is exhausted. Callers should treat False as
    "reject" and must still call this on the rejected attempt, so a client
    hammering the endpoint stays locked out for the whole window.
    """
    max_hits, window = limit
    timestamp = int(now if now is not None else time.time())
    window_start = timestamp - (timestamp % window)

    conn.execute(
        "INSERT INTO rate_limits (bucket, window_start, hits) VALUES (?, ?, 1)"
        " ON CONFLICT(bucket, window_start) DO UPDATE SET hits = hits + 1",
        (bucket, window_start),
    )
    row = conn.execute(
        "SELECT hits FROM rate_limits WHERE bucket = ? AND window_start = ?",
        (bucket, window_start),
    ).fetchone()
    return int(row["hits"]) <= max_hits


def purge_expired(conn: sqlite3.Connection, *, older_than_seconds: int = 24 * 60 * 60) -> int:
    """Drop stale counter rows. Returns how many went."""
    cutoff = int(time.time()) - older_than_seconds
    cursor = conn.execute("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
    return cursor.rowcount
