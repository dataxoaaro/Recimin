"""The job loop.

Exactly one job at a time. That is a requirement, not a default: gallery-dl
ships a 6-12 second sleep for Instagram by default, which is what its
maintainer thinks of Meta's per-IP tolerance. Parallel imports are how a
residential address gets throttled.
"""

import asyncio
import contextlib
import logging
import sqlite3
from collections.abc import Awaitable, Callable

from recimin import push
from recimin.config import Settings
from recimin.db.models import Job, JobStatus
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import recipes as recipes_repo

logger = logging.getLogger(__name__)

IDLE_POLL_SECONDS = 3.0
BACKOFF_BASE_SECONDS = 2.0

Handler = Callable[[sqlite3.Connection, Job, Settings], Awaitable[int | None]]


class NonRetryable(Exception):
    """The job cannot succeed by trying again.

    Raised when an extractor is broken or a page genuinely has no recipe —
    cases where a human has to look. Goes straight to needs_attention rather
    than burning three attempts first.
    """


def _notify(conn: sqlite3.Connection, settings: Settings, **kwargs: str) -> None:
    """Send a push, swallowing anything that goes wrong.

    A failed notification must never fail the import that triggered it: the
    recipe is already saved either way.
    """
    try:
        push.notify(conn, settings, **kwargs)  # type: ignore[arg-type]
    except Exception:
        logger.exception("push notification failed")


async def run_once(conn: sqlite3.Connection, settings: Settings, handler: Handler) -> Job | None:
    """Claim and process a single job. Returns the job, or None if idle."""
    job = jobs_repo.claim_next(conn)
    if job is None:
        return None

    logger.info(
        "job started",
        extra={"job_id": job.id, "platform": job.platform, "attempt": job.attempts},
    )
    try:
        recipe_id = await handler(conn, job, settings)
    except asyncio.CancelledError:
        # Shutdown mid-flight. Return the job to the queue without counting an
        # attempt, and re-raise so the caller still unwinds.
        #
        # This must live here, not in run_forever's finally: at cancellation
        # time run_once has not returned, so the caller has no reference to the
        # job it would need to release.
        jobs_repo.release(conn, job.id)
        logger.info("released in-flight job", extra={"job_id": job.id})
        raise
    except NonRetryable as error:
        jobs_repo.fail(conn, job.id, str(error), retryable=False)
        logger.warning("job needs attention", extra={"job_id": job.id, "error": str(error)})
        _notify(conn, settings, title="Import failed", body=str(error)[:120], url="/imports")
    except Exception as error:
        status = jobs_repo.fail(conn, job.id, f"{type(error).__name__}: {error}")
        logger.exception("job failed", extra={"job_id": job.id, "outcome": str(status)})
        if status is JobStatus.QUEUED:
            # Exponential backoff before the retry becomes claimable again.
            await asyncio.sleep(BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)))
        else:
            _notify(conn, settings, title="Import failed", body=str(error)[:120], url="/imports")
    else:
        jobs_repo.finish(conn, job.id, recipe_id=recipe_id)
        logger.info("job done", extra={"job_id": job.id, "recipe_id": recipe_id})
        recipe = recipes_repo.get(conn, recipe_id) if recipe_id else None
        _notify(
            conn,
            settings,
            title="Recipe saved",
            body=recipe.title if recipe else "Import finished",
            url=f"/recipes/{recipe_id}" if recipe_id else "/",
        )

    return job


async def run_forever(
    conn: sqlite3.Connection,
    settings: Settings,
    handler: Handler,
    stop: asyncio.Event,
) -> None:
    """Drain the queue until asked to stop.

    Any job left running by a previous crash is returned to the queue first: a
    running row with no live worker would otherwise sit there forever.
    """
    reclaimed = jobs_repo.reclaim_stale(conn)
    if reclaimed:
        logger.info("reclaimed stale jobs", extra={"count": reclaimed})

    while not stop.is_set():
        # run_once releases its own job on cancellation.
        if await run_once(conn, settings, handler) is None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=IDLE_POLL_SECONDS)
