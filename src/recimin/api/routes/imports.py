"""Import queueing and job status.

POST /api/import must return within a few hundred milliseconds: the iOS
Shortcut is waiting on it, and the user is still inside Instagram. It writes a
row and returns 202. Everything else happens in the worker.
"""

import logging

from fastapi import APIRouter, HTTPException, UploadFile, status

from recimin.api.deps import CurrentUser, DbDep, ImportCaller, SettingsDep
from recimin.api.schemas import ImportAccepted, ImportRequest, JobOut
from recimin.db.models import MediaKind
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import media as media_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.importer.urls import UrlRejected, classify
from recimin.media import store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["imports"])

# One recipe rarely spans more than a few pages; a hard cap keeps a single
# request from becoming a bulk uploader.
MAX_PHOTOS = 8
_PHOTO_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})


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


@router.post("/import/photos", response_model=ImportAccepted, status_code=status.HTTP_202_ACCEPTED)
def queue_photo_import(
    files: list[UploadFile], user: ImportCaller, conn: DbDep, settings: SettingsDep
) -> ImportAccepted:
    """Queue photos or screenshots for import.

    The images are stored immediately — the phone should not have to keep the
    connection open while a model reads them — and the worker does the rest.
    This path requires the LLM; without a key the job lands in needs_attention
    with a message saying so.
    """
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send at least one image")
    if len(files) > MAX_PHOTOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_PHOTOS} images per import"
        )
    for file in files:
        if (file.content_type or "") not in _PHOTO_MIMES:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"Unsupported file type: {file.content_type or 'unknown'}",
            )

    total_upload = sum(file.size or 0 for file in files)
    if media_repo.total_bytes(conn) + total_upload > settings.max_media_bytes:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "Media storage limit reached")

    media_ids: list[int] = []
    for position, file in enumerate(files):
        try:
            stored = store.store_stream(
                file.file, file.content_type or "", media_dir=settings.data_dir
            )
        except store.MediaTooLarge:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE, "An image is too large"
            ) from None
        existing = media_repo.find_by_sha256(conn, stored.sha256)
        if existing is not None:
            media_ids.append(existing.id)
            continue
        media_ids.append(
            media_repo.create(
                conn,
                kind=MediaKind.IMAGE,
                file_path=stored.relative_path,
                sha256=stored.sha256,
                bytes_=stored.bytes,
                mime=stored.mime,
                position=position,
            )
        )

    job_id = jobs_repo.enqueue(
        conn,
        input_url="photos",
        kind="image",
        created_by=user.id,
        media_ids=media_ids,
    )
    logger.info("photo import queued", extra={"job_id": job_id, "images": len(media_ids)})
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
