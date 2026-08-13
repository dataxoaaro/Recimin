"""Import queueing and job status.

POST /api/import must return within a few hundred milliseconds: the iOS
Shortcut is waiting on it, and the user is still inside Instagram. It writes a
row and returns 202. Everything else happens in the worker.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from recimin.api.deps import CurrentUser, DbDep, ImportCaller
from recimin.api.schemas import ImportAccepted, ImportRequest, JobOut
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.importer.urls import UrlRejected, classify

logger = logging.getLogger(__name__)
router = APIRouter(tags=["imports"])


@router.post("/import", response_model=ImportAccepted, status_code=status.HTTP_202_ACCEPTED)
def queue_import(body: ImportRequest, user: ImportCaller, conn: DbDep) -> ImportAccepted:
    """Queue a URL for import.

    Accepts a session cookie or a device bearer token — this is the only route
    that takes a token, because the Shortcut cannot do a cookie login.
    """
    try:
        classified = classify(body.url)
    except UrlRejected as rejected:
        # 422 rather than 400: the URL is well-formed, it is just not importable.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(rejected)) from None

    # Short links hide their real target, so dedupe waits for the worker to
    # follow them. Everything else can be checked now and answered instantly.
    if not classified.needs_redirect_resolution:
        existing = recipes_repo.get_by_normalised_url(conn, classified.normalised)
        if existing is not None:
            logger.info(
                "duplicate import", extra={"recipe_id": existing.id, "url": classified.normalised}
            )
            return ImportAccepted(job_id=0, duplicate=True, recipe_id=existing.id)

    job_id = jobs_repo.enqueue(
        conn,
        input_url=body.url,
        normalised_url=classified.normalised,
        platform=str(classified.platform),
        created_by=user.id,
    )
    logger.info(
        "import queued",
        extra={"job_id": job_id, "platform": str(classified.platform)},
    )
    return ImportAccepted(job_id=job_id)


@router.get("/imports", response_model=list[JobOut])
def list_imports(_: CurrentUser, conn: DbDep) -> list[JobOut]:
    """Recent jobs, newest first."""
    return [JobOut.model_validate(job, from_attributes=True) for job in jobs_repo.recent(conn)]


@router.post("/imports/{job_id}/retry", response_model=JobOut)
def retry_import(job_id: int, _: CurrentUser, conn: DbDep) -> JobOut:
    """Re-queue a failed job and reset its attempt counter."""
    if jobs_repo.get(conn, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    if not jobs_repo.requeue(conn, job_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "That import is not in a failed state")

    job = jobs_repo.get(conn, job_id)
    if job is None:  # pragma: no cover - defensive
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return JobOut.model_validate(job, from_attributes=True)
