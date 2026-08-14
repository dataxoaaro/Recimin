"""Media upload and serving.

Bytes are served through the API rather than by a static mount so they inherit
the session check. A household recipe library is private.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from recimin.api.deps import CurrentUser, DbDep, SettingsDep
from recimin.db.models import MediaKind
from recimin.db.repositories import media as media_repo
from recimin.media import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/media", tags=["media"])

_KIND_BY_PREFIX = {
    "image/": MediaKind.IMAGE,
    "video/": MediaKind.VIDEO,
    "audio/": MediaKind.AUDIO,
}


# Multipart boundaries and part headers on top of the file itself.
_MULTIPART_OVERHEAD = 16 * 1024


def _reject_oversized_body(request: Request) -> None:
    """Refuse before the multipart parser spools gigabytes to temp storage.

    Dependencies resolve before the body is parsed, so an honest client is
    turned away without the server reading its upload. Content-Length can lie,
    which is why store_stream re-enforces the cap byte by byte.
    """
    declared = request.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > store.MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is too large")


@router.post(
    "", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_reject_oversized_body)]
)
def upload(
    file: UploadFile,
    _: CurrentUser,
    conn: DbDep,
    settings: SettingsDep,
    recipe_id: int | None = None,
) -> dict[str, object]:
    """Store an uploaded file and record it.

    Sync on purpose: FastAPI runs it in the threadpool, so the hash and the
    fsync never stall the event loop the way the previous async version did.
    """
    mime = file.content_type or ""

    if media_repo.total_bytes(conn) + (file.size or 0) > settings.max_media_bytes:
        raise HTTPException(status.HTTP_507_INSUFFICIENT_STORAGE, "Media storage limit reached")

    try:
        stored = store.store_stream(file.file, mime, media_dir=settings.data_dir)
    except store.UnsupportedMediaType:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type: {mime}"
        ) from None
    except store.MediaTooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is too large") from None

    existing = media_repo.find_by_sha256(conn, stored.sha256)
    if existing is not None:
        # One row per unique file — file_path is UNIQUE, so inserting a second
        # row for the same bytes is not an option. If they arrived as an
        # orphan earlier (an upload without a recipe), claim them now.
        if existing.recipe_id is None and recipe_id is not None:
            media_repo.attach_to_recipe(conn, existing.id, recipe_id)
        return {"id": existing.id, "bytes": existing.bytes, "deduplicated": True}

    kind = next(
        (k for prefix, k in _KIND_BY_PREFIX.items() if mime.startswith(prefix)),
        MediaKind.IMAGE,
    )
    media_id = media_repo.create(
        conn,
        kind=kind,
        file_path=stored.relative_path,
        sha256=stored.sha256,
        bytes_=stored.bytes,
        mime=stored.mime,
        recipe_id=recipe_id,
    )
    return {"id": media_id, "bytes": stored.bytes, "deduplicated": stored.deduplicated}


@router.get("/{media_id}")
def serve(media_id: int, _: CurrentUser, conn: DbDep, settings: SettingsDep) -> FileResponse:
    """Stream a stored file behind the session cookie."""
    record = media_repo.get(conn, media_id)
    if record is None or record.discarded_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    path = store.absolute_path(record.file_path, media_dir=settings.data_dir)
    if not path.is_file():
        # The row outlived its bytes. Report it rather than 500.
        logger.warning("media row without a file", extra={"media_id": media_id})
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    return FileResponse(
        path,
        media_type=record.mime,
        # Immutable, not five minutes. Storage is content-addressed, so a given
        # media id always resolves to the same bytes — editing a recipe's photo
        # mints a new id rather than changing this one. At max-age=300 a phone
        # on mobile data refetched every hero image on any visit five minutes
        # apart, for bytes it already had. `private` keeps it out of the
        # Cloudflare edge cache, which matters because the route is behind auth.
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
