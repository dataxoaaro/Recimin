"""Content-addressed media storage.

Files live on disk under a sha256-derived path; the database holds only
metadata. Writes are atomic — temp file, fsync, rename — so a crash mid-write
cannot leave a truncated file that later looks valid.

Identical bytes are stored once. Two recipes sharing a hero image share the
file, and re-importing the same post never rewrites it.
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

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


class UnsupportedMediaType(ValueError):
    """The MIME type is not on the allowlist."""


class MediaTooLarge(ValueError):
    """A single file exceeded the per-upload cap."""


class StorageFull(RuntimeError):
    """Storing this file would cross the configured total-bytes guard."""


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


def store_bytes(payload: bytes, mime: str, *, media_dir: Path) -> StoredFile:
    """Write bytes into the store and return their address.

    media_dir is the parent of the `media/` tree — normally the data directory.
    """
    if mime not in EXTENSIONS:
        raise UnsupportedMediaType(mime)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise MediaTooLarge(f"{len(payload)} bytes")

    digest = hashlib.sha256(payload).hexdigest()
    relative = relative_path_for(digest, EXTENSIONS[mime])
    destination = media_dir / relative

    if destination.exists():
        # Same bytes, same path. Nothing to do.
        return StoredFile(relative, digest, len(payload), mime, deduplicated=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(destination)

    logger.info("media stored", extra={"sha256": digest, "bytes": len(payload), "mime": mime})
    return StoredFile(relative, digest, len(payload), mime, deduplicated=False)


def absolute_path(relative: str, *, media_dir: Path) -> Path:
    """Resolve a stored path, refusing anything that escapes the media tree."""
    candidate = (media_dir / relative).resolve()
    root = media_dir.resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"path escapes the media directory: {relative}")
    return candidate


def delete_file(relative: str, *, media_dir: Path) -> bool:
    """Remove the bytes for a discarded file. The database row is kept."""
    path = absolute_path(relative, media_dir=media_dir)
    if not path.is_file():
        return False
    path.unlink()
    return True
