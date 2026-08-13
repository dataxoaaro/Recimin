"""Instagram and TikTok import.

Routing, per Appendix A:

  TikTok /photo/  -> gallery-dl. yt-dlp's regex matches only /video/ and it has
                     no imagePost handling at all, so slideshows fall through
                     to the generic extractor and fail. Slideshows are a common
                     recipe format.
  TikTok /video/  -> yt-dlp with a Chrome UA.
  Instagram       -> yt-dlp with a Chrome UA.

No session cookies, ever. Platform terms bind *users*; a logged-out visitor
without an account never assents to them, and holding an account binds you for
that period whether or not you later close it.
"""

import asyncio
import logging
import mimetypes
import shutil
import sqlite3
import tempfile
from pathlib import Path

from recimin.config import Settings
from recimin.db.models import MediaKind
from recimin.db.repositories import media as media_repo
from recimin.importer import caption as caption_gate
from recimin.importer import gallerydl, ytdlp
from recimin.importer.normalise import NormalisedRecipe
from recimin.importer.urls import Classified, Platform
from recimin.media import store

logger = logging.getLogger(__name__)

VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
SUBTITLE_SUFFIXES = frozenset({".vtt", ".srt"})

# Storing an mp4 costs 5-30MB; a subtitle track costs kilobytes and is the
# single most useful text after the caption.
KEEP_SUFFIXES = VIDEO_SUFFIXES | IMAGE_SUFFIXES


class SocialFetchFailed(Exception):
    """The post could not be fetched."""

    def __init__(self, message: str, *, needs_update: bool = False) -> None:
        super().__init__(message)
        self.needs_update = needs_update


async def fetch_metadata(classified: Classified, settings: Settings) -> ytdlp.PostMetadata:
    """Caption and post identity, without downloading media."""
    try:
        return await ytdlp.fetch_metadata(classified.normalised, settings)
    except ytdlp.YtDlpError as error:
        raise SocialFetchFailed(str(error), needs_update=error.needs_update) from error


async def download_media(classified: Classified, settings: Settings) -> tuple[list[Path], str]:
    """Download a post's media into a temp directory.

    Returns the media files and any subtitle text found. The caller must copy
    what it wants into the store before the directory is cleaned up.
    """
    workdir = Path(tempfile.mkdtemp(prefix="recimin-"))
    try:
        if classified.platform is Platform.TIKTOK and classified.is_photo_post:
            files = await gallerydl.download(classified.normalised, workdir, settings)
        else:
            try:
                files = await ytdlp.download(classified.normalised, workdir, settings)
            except ytdlp.YtDlpError as error:
                if classified.platform is not Platform.TIKTOK:
                    raise SocialFetchFailed(str(error), needs_update=error.needs_update) from error
                # gallery-dl is the more robust TikTok path when yt-dlp breaks.
                logger.warning(
                    "yt-dlp failed on TikTok, trying gallery-dl", extra={"error": str(error)}
                )
                files = await gallerydl.download(classified.normalised, workdir, settings)

        subtitles = _read_subtitles(files)
        media = [f for f in files if f.suffix.lower() in KEEP_SUFFIXES]
        return media, subtitles
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise


def _read_subtitles(files: list[Path]) -> str:
    """Flatten any downloaded subtitle track to plain text.

    TikTok publishes its own auto-captions, which cost nothing and beat ASR.
    Instagram has no equivalent.
    """
    lines: list[str] = []
    for path in files:
        if path.suffix.lower() not in SUBTITLE_SUFFIXES:
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.isdigit() or "-->" in line or line.startswith("WEBVTT"):
                continue
            if line not in lines[-3:]:  # auto-captions repeat heavily
                lines.append(line)
    return " ".join(lines)


def store_media(
    conn: sqlite3.Connection,
    files: list[Path],
    *,
    settings: Settings,
    source_url: str,
) -> list[int]:
    """Copy downloaded files into the content-addressed store.

    Bytes are persisted during the import job on purpose: Instagram media URLs
    live 33-105 hours and TikTok's exactly 48, and Instagram's expiry parameter
    is hex-encoded so it reads as the year 4000 if parsed as decimal.
    """
    # The caller's order is meaningful: it puts a generated poster first so it
    # becomes the hero. Sorting here would silently reorder that, and
    # "clip.mp4" sorts before "clip_poster.jpg" because '.' < '_'.
    media_ids: list[int] = []
    for position, path in enumerate(files):
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if mime not in store.EXTENSIONS:
            logger.info("skipping unsupported file", extra={"name": path.name, "mime": mime})
            continue
        try:
            stored = store.store_bytes(path.read_bytes(), mime, media_dir=settings.data_dir)
        except (store.MediaTooLarge, store.UnsupportedMediaType) as error:
            logger.warning("media rejected", extra={"name": path.name, "error": str(error)})
            continue

        existing = media_repo.find_by_sha256(conn, stored.sha256)
        if existing is not None:
            media_ids.append(existing.id)
            continue

        media_ids.append(
            media_repo.create(
                conn,
                kind=MediaKind.VIDEO if path.suffix.lower() in VIDEO_SUFFIXES else MediaKind.IMAGE,
                file_path=stored.relative_path,
                sha256=stored.sha256,
                bytes_=stored.bytes,
                mime=stored.mime,
                position=position,
                source_url=source_url,
            )
        )
    return media_ids


def draft_from_caption(
    metadata: ytdlp.PostMetadata, classified: Classified, subtitles: str
) -> NormalisedRecipe:
    """Build a draft from the caption alone.

    Without an LLM this is as far as extraction goes, and it is still worth
    having: the media is archived, the caption is preserved, and the recipe is
    a draft the user finishes by hand. Phase 8 replaces the body of this.
    """
    body = caption_gate.strip_hashtags(metadata.caption)
    if subtitles:
        body = f"{body}\n\n---\n\nTranscript:\n{subtitles}" if body else subtitles

    return NormalisedRecipe(
        title=caption_gate.title_from_caption(
            metadata.caption, fallback=f"{classified.platform} post {metadata.post_id}"
        ),
        ingredients=[],
        instructions_md=body,
        author=metadata.uploader,
        language="fi" if _looks_finnish(metadata.caption) else "en",
    )


def _looks_finnish(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in (" dl ", " rkl ", " tl ", "ää", "öö", "ja "))


async def cleanup(paths: list[Path]) -> None:
    """Remove the temp directory a download used."""
    for parent in {p.parent for p in paths}:
        await asyncio.to_thread(shutil.rmtree, parent, True)
