"""Content-addressed media storage.

Files live on disk under a sha256-derived path; the database holds only
metadata. Writes are atomic — temp file, fsync, rename — so a crash mid-write
cannot leave a truncated file that later looks valid.

Identical bytes are stored once. Two recipes sharing a hero image share the
file, and re-importing the same post never rewrites it.
"""

import hashlib
import io
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Deliberately narrow. Anything not on this list is refused rather than guessed.
EXTENSIONS: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "audio/mp4": "m4a",
    "audio/mpeg": "mp3",
}

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CHUNK_BYTES = 1 << 20


class UnsupportedMediaType(ValueError):
    """The MIME type is not on the allowlist."""


class MediaTooLarge(ValueError):
    """A single file exceeded the per-upload cap."""


@dataclass(frozen=True, slots=True)
class StoredFile:
    """The result of writing bytes to the store."""

    relative_path: str
    sha256: str
    bytes: int
    mime: str
    deduplicated: bool


def relative_path_for(sha256: str, extension: str) -> str:
    """Two-character fan-out, so no directory ends up with a million entries."""
    return f"media/{sha256[:2]}/{sha256}.{extension}"


def store_stream(source: BinaryIO, mime: str, *, media_dir: Path) -> StoredFile:
    """Stream bytes into the store, hashing as they arrive.

    media_dir is the parent of the `media/` tree — normally the data directory.

    The content address is only known once the last byte is hashed, so the
    stream lands in a temp file and is renamed into place. The size cap is
    enforced per chunk: an oversized upload is rejected 25MB in, not after it
    has been read whole into memory.
    """
    if mime not in EXTENSIONS:
        raise UnsupportedMediaType(mime)

    (media_dir / "media").mkdir(parents=True, exist_ok=True)
    temporary = media_dir / "media" / f".incoming-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    total = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := source.read(CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise MediaTooLarge(f"more than {MAX_UPLOAD_BYTES} bytes")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    sha256 = digest.hexdigest()
    relative = relative_path_for(sha256, EXTENSIONS[mime])
    destination = media_dir / relative

    if destination.exists():
        # Same bytes, same path. Nothing to do.
        temporary.unlink(missing_ok=True)
        return StoredFile(relative, sha256, total, mime, deduplicated=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary.replace(destination)

    logger.info("media stored", extra={"sha256": sha256, "bytes": total, "mime": mime})
    return StoredFile(relative, sha256, total, mime, deduplicated=False)


def store_bytes(payload: bytes, mime: str, *, media_dir: Path) -> StoredFile:
    """Write in-memory bytes into the store. See store_stream."""
    if mime in EXTENSIONS and len(payload) > MAX_UPLOAD_BYTES:
        raise MediaTooLarge(f"{len(payload)} bytes")
    return store_stream(io.BytesIO(payload), mime, media_dir=media_dir)


def absolute_path(relative: str, *, media_dir: Path) -> Path:
    """Resolve a stored path, refusing anything that escapes the media tree."""
    candidate = (media_dir / relative).resolve()
    root = media_dir.resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"path escapes the media directory: {relative}")
    return candidate


def delete_file(relative: str, *, media_dir: Path) -> bool:
    """Remove the bytes for a file whose last referencing row is gone."""
    path = absolute_path(relative, media_dir=media_dir)
    if not path.is_file():
        return False
    path.unlink()
    return True
