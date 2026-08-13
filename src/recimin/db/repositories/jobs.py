"""Import jobs.

The only channel between the api and worker containers. The api writes queued
rows; the worker claims and advances them.
"""

import sqlite3

from recimin.db.clock import now
from recimin.db.connection import transaction
from recimin.db.models import CaptionGate, Job, JobStage, JobStatus

MAX_ATTEMPTS = 3

TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.NEEDS_ATTENTION})


def enqueue(
    conn: sqlite3.Connection,
    *,
    input_url: str,
    normalised_url: str | None = None,
    platform: str | None = None,
    created_by: int | None = None,
) -> int:
    """Queue an import. Must be fast: the Shortcut waits on this response."""
    cursor = conn.execute(
        "INSERT INTO jobs (kind, status, input_url, normalised_url, platform,"
        " created_by, created_at) VALUES ('import', 'queued', ?, ?, ?, ?, ?)",
        (input_url, normalised_url, platform, created_by, now()),
    )
    return int(cursor.lastrowid or 0)


def get(conn: sqlite3.Connection, job_id: int) -> Job | None:
    """Fetch one job, or None."""
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return Job.from_row(row) if row else None


def claim_next(conn: sqlite3.Connection) -> Job | None:
    """Atomically take the oldest queued job and mark it running.

    The UPDATE ... WHERE status='queued' inside a transaction is what guarantees
    a job is never claimed twice, even though the worker runs one at a time
    today. Returns None when the queue is empty.
    """
    with transaction(conn):
        row = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        cursor = conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ?, attempts = attempts + 1"
            " WHERE id = ? AND status = 'queued'",
            (now(), row["id"]),
        )
        if cursor.rowcount == 0:
            return None
        claimed = conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
    return Job.from_row(claimed)


def set_stage(conn: sqlite3.Connection, job_id: int, stage: JobStage) -> None:
    """Record progress within a running job so the UI can show it."""
    conn.execute("UPDATE jobs SET stage = ? WHERE id = ?", (str(stage), job_id))


def set_caption_gate(conn: sqlite3.Connection, job_id: int, gate: CaptionGate) -> None:
    """Record whether the caption alone carried the recipe."""
    conn.execute("UPDATE jobs SET caption_gate = ? WHERE id = ?", (str(gate), job_id))


def finish(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    recipe_id: int | None = None,
    normalised_url: str | None = None,
    platform: str | None = None,
) -> None:
    """Mark a job done."""
    conn.execute(
        "UPDATE jobs SET status = 'done', stage = NULL, finished_at = ?, recipe_id = ?,"
        " normalised_url = coalesce(?, normalised_url),"
        " platform = coalesce(?, platform), last_error = NULL WHERE id = ?",
        (now(), recipe_id, normalised_url, platform, job_id),
    )


def fail(conn: sqlite3.Connection, job_id: int, error: str, *, retryable: bool = True) -> JobStatus:
    """Record a failure.

    A retryable job goes back to the queue until MAX_ATTEMPTS, then fails. A
    non-retryable one goes straight to needs_attention, which means a human must
    look — usually because an extractor broke rather than because the URL was bad.
    Returns the resulting status.
    """
    row = conn.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
    attempts = int(row["attempts"]) if row else MAX_ATTEMPTS

    if not retryable:
        status = JobStatus.NEEDS_ATTENTION
    elif attempts < MAX_ATTEMPTS:
        status = JobStatus.QUEUED
    else:
        status = JobStatus.FAILED

    finished = None if status is JobStatus.QUEUED else now()
    conn.execute(
        "UPDATE jobs SET status = ?, last_error = ?, finished_at = ? WHERE id = ?",
        (str(status), error[:2000], finished, job_id),
    )
    return status


def release(conn: sqlite3.Connection, job_id: int) -> None:
    """Return a running job to the queue without counting a failure.

    Used on graceful shutdown so a job interrupted mid-flight is retried rather
    than burning an attempt.
    """
    conn.execute(
        "UPDATE jobs SET status = 'queued', stage = NULL, started_at = NULL,"
        " attempts = max(attempts - 1, 0) WHERE id = ? AND status = 'running'",
        (job_id,),
    )


def requeue(conn: sqlite3.Connection, job_id: int) -> bool:
    """Manual retry from the Imports screen. Resets the attempt counter."""
    cursor = conn.execute(
        "UPDATE jobs SET status = 'queued', attempts = 0, last_error = NULL,"
        " stage = NULL, started_at = NULL, finished_at = NULL"
        " WHERE id = ? AND status IN ('failed', 'needs_attention')",
        (job_id,),
    )
    return cursor.rowcount > 0


def reclaim_stale(conn: sqlite3.Connection) -> int:
    """Return jobs left running by a crashed worker to the queue.

    Called at worker startup. A running job with no live worker would otherwise
    sit there forever.
    """
    cursor = conn.execute(
        "UPDATE jobs SET status = 'queued', stage = NULL, started_at = NULL"
        " WHERE status = 'running'"
    )
    return cursor.rowcount


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[Job]:
    """Newest jobs first, for the Imports screen."""
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [Job.from_row(row) for row in rows]


def queue_depth(conn: sqlite3.Connection) -> int:
    """How many jobs are waiting, for /health."""
    return int(
        conn.execute("SELECT count(*) AS n FROM jobs WHERE status = 'queued'").fetchone()["n"]
    )
