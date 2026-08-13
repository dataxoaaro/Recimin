"""The import endpoint and the worker loop."""

import asyncio
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from recimin.config import Settings
from recimin.db.models import Job, JobStatus
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories.recipes import RecipeDraft
from recimin.worker import loop
from recimin.worker.loop import NonRetryable, run_forever, run_once

IG_POST = "https://www.instagram.com/p/DWjfQTDNm_l/"


# ─── the endpoint ────────────────────────────────────────────────────────


def test_queues_and_returns_202(auth_client: TestClient) -> None:
    response = auth_client.post("/api/import", json={"url": IG_POST})
    assert response.status_code == 202
    assert response.json()["job_id"] > 0
    assert response.json()["duplicate"] is False


def test_responds_fast_enough_for_the_shortcut(auth_client: TestClient) -> None:
    """The Shortcut blocks on this while the user is still inside Instagram."""
    started = time.perf_counter()
    for index in range(10):
        auth_client.post("/api/import", json={"url": f"{IG_POST}?igsh={index}"})
    elapsed_ms = (time.perf_counter() - started) * 1000 / 10
    assert elapsed_ms < 300, f"{elapsed_ms:.0f}ms per request"


def test_tracking_params_collapse_to_one_job(
    auth_client: TestClient, db: sqlite3.Connection
) -> None:
    auth_client.post("/api/import", json={"url": f"{IG_POST}?igsh=aaa"})
    auth_client.post("/api/import", json={"url": f"{IG_POST}?igsh=bbb"})
    urls = {job.normalised_url for job in jobs_repo.recent(db)}
    assert urls == {"https://instagram.com/p/DWjfQTDNm_l"}


def test_existing_recipe_reports_duplicate_rather_than_erroring(
    auth_client: TestClient, db: sqlite3.Connection
) -> None:
    recipe_id = recipes_repo.create(
        db,
        RecipeDraft(
            title="Already here", source_url_normalised="https://instagram.com/p/DWjfQTDNm_l"
        ),
    )
    response = auth_client.post("/api/import", json={"url": IG_POST})
    assert response.status_code == 202
    assert response.json() == {"job_id": 0, "duplicate": True, "recipe_id": recipe_id}


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        ("https://www.instagram.com/kinuskikissa/", "individual post"),
        ("https://www.tiktok.com/@kinuskikissa", "individual post"),
        ("https://www.valio.fi/", "No recipe found"),
    ],
)
def test_profiles_and_roots_are_refused_without_a_job(
    auth_client: TestClient, db: sqlite3.Connection, url: str, fragment: str
) -> None:
    response = auth_client.post("/api/import", json={"url": url})
    assert response.status_code == 422
    assert fragment in response.json()["detail"]
    assert jobs_repo.recent(db) == []


def test_import_accepts_a_device_token(auth_client: TestClient) -> None:
    """The whole reason device tokens exist."""
    token = auth_client.post("/api/tokens", json={"name": "iPhone"}).json()["token"]
    bare = TestClient(auth_client.app)
    response = bare.post(
        "/api/import",
        json={"url": IG_POST},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202


def test_import_refuses_an_unknown_token(auth_client: TestClient) -> None:
    bare = TestClient(auth_client.app)
    response = bare.post(
        "/api/import", json={"url": IG_POST}, headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


def test_retry_only_applies_to_failed_jobs(auth_client: TestClient, db: sqlite3.Connection) -> None:
    job_id = auth_client.post("/api/import", json={"url": IG_POST}).json()["job_id"]
    assert auth_client.post(f"/api/imports/{job_id}/retry").status_code == 409

    jobs_repo.claim_next(db)
    jobs_repo.fail(db, job_id, "broke", retryable=False)
    assert auth_client.post(f"/api/imports/{job_id}/retry").status_code == 200
    assert auth_client.post("/api/imports/9999/retry").status_code == 404


def test_imports_list_is_newest_first(auth_client: TestClient) -> None:
    auth_client.post("/api/import", json={"url": IG_POST})
    auth_client.post("/api/import", json={"url": "https://valio.fi/reseptit/x"})
    listed = auth_client.get("/api/imports").json()
    assert len(listed) == 2
    assert listed[0]["input_url"].endswith("/reseptit/x")


# ─── the worker loop ─────────────────────────────────────────────────────


async def _ok(conn: sqlite3.Connection, job: Job, settings: Settings) -> int | None:
    return None


async def test_idle_loop_returns_none(db: sqlite3.Connection, settings: Settings) -> None:
    assert await run_once(db, settings, _ok) is None


async def test_successful_job_finishes(db: sqlite3.Connection, settings: Settings) -> None:
    job_id = jobs_repo.enqueue(db, input_url=IG_POST)
    await run_once(db, settings, _ok)
    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.DONE
    assert job.stage is None


async def test_non_retryable_goes_straight_to_needs_attention(
    db: sqlite3.Connection, settings: Settings
) -> None:
    async def broken(conn: sqlite3.Connection, job: Job, s: Settings) -> int | None:
        raise NonRetryable("yt-dlp cannot extract this")

    job_id = jobs_repo.enqueue(db, input_url=IG_POST)
    await run_once(db, settings, broken)

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.NEEDS_ATTENTION
    assert job.attempts == 1, "a broken extractor must not burn three attempts"


async def test_transient_failure_retries_then_fails(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(loop, "BACKOFF_BASE_SECONDS", 0.0)
    attempts = 0

    async def flaky(conn: sqlite3.Connection, job: Job, s: Settings) -> int | None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("network")

    job_id = jobs_repo.enqueue(db, input_url=IG_POST)
    for _ in range(jobs_repo.MAX_ATTEMPTS):
        await run_once(db, settings, flaky)

    assert attempts == jobs_repo.MAX_ATTEMPTS
    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.FAILED


async def test_the_loop_survives_a_handler_that_raises_anything(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashing handler must never take the worker down with it."""
    monkeypatch.setattr(loop, "BACKOFF_BASE_SECONDS", 0.0)

    async def catastrophe(conn: sqlite3.Connection, job: Job, s: Settings) -> int | None:
        raise SystemError("something truly unexpected")

    jobs_repo.enqueue(db, input_url=IG_POST)
    assert await run_once(db, settings, catastrophe) is not None


async def test_jobs_run_strictly_one_at_a_time(db: sqlite3.Connection, settings: Settings) -> None:
    """Parallel imports are what get a residential IP throttled."""
    concurrent = 0
    peak = 0

    async def slow(conn: sqlite3.Connection, job: Job, s: Settings) -> int | None:
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0.02)
        concurrent -= 1
        return None

    for index in range(3):
        jobs_repo.enqueue(db, input_url=f"{IG_POST}?n={index}")

    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(db, settings, slow, stop))
    await asyncio.sleep(0.2)
    stop.set()
    await task

    assert peak == 1
    assert jobs_repo.queue_depth(db) == 0


async def test_shutdown_releases_the_in_flight_job(
    db: sqlite3.Connection, settings: Settings
) -> None:
    """An interrupted job is retried later without burning an attempt."""
    started = asyncio.Event()

    async def hang(conn: sqlite3.Connection, job: Job, s: Settings) -> int | None:
        started.set()
        await asyncio.sleep(5)
        return None

    job_id = jobs_repo.enqueue(db, input_url=IG_POST)
    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(db, settings, hang, stop))
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.QUEUED
    assert job.attempts == 0


async def test_startup_reclaims_a_crashed_workers_job(
    db: sqlite3.Connection, settings: Settings
) -> None:
    jobs_repo.enqueue(db, input_url=IG_POST)
    jobs_repo.claim_next(db)  # simulate a crash mid-job

    stop = asyncio.Event()
    task = asyncio.create_task(run_forever(db, settings, _ok, stop))
    await asyncio.sleep(0.05)
    stop.set()
    await task

    assert jobs_repo.queue_depth(db) == 0
