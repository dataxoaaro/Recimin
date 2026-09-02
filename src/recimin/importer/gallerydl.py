"""gallery-dl adapter.

Exists for exactly one reason: TikTok photo-slideshow posts. yt-dlp's TikTok
regex matches only /video/ and the extractor has no imagePost handling, so a
/photo/ URL falls through to the generic extractor and fails. gallery-dl
matches /(?:phot|vide)o/ and iterates imagePost.images.

It also serves as the TikTok fallback when yt-dlp breaks, which it does a few
times a year.
"""

import asyncio
import json
import logging
from pathlib import Path

from recimin.config import Settings
from recimin.importer.ytdlp import PostMetadata

logger = logging.getLogger(__name__)

TIMEOUT = 600
TIMEOUT_METADATA = 90


class GalleryDlError(Exception):
    """gallery-dl failed."""


async def _dump_json(url: str, settings: Settings, timeout: int) -> object:
    process = await asyncio.create_subprocess_exec(
        "gallery-dl",
        "--user-agent",
        settings.scraper_user_agent,
        "--simulate",
        "--dump-json",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise GalleryDlError(f"timed out after {timeout}s") from None

    if process.returncode != 0 or not stdout.strip():
        detail = stderr.decode("utf-8", errors="replace")[:500]
        raise GalleryDlError(detail or f"exit {process.returncode}")

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as error:
        raise GalleryDlError(f"unparseable metadata: {error}") from error


def _first_post(payload: object) -> dict[str, object] | None:
    """The first row carrying real post metadata, if any.

    gallery-dl emits a list of [type, url, metadata] rows. A short link yields
    only a redirect row whose metadata holds nothing but the category.
    """
    if not isinstance(payload, list):
        return None
    for row in payload:
        is_row = isinstance(row, list) and len(row) > 2 and isinstance(row[2], dict)
        if is_row and ("id" in row[2] or "desc" in row[2]):
            return row[2]
    return None


def _redirect_target(payload: object) -> str | None:
    """The canonical URL a vm.tiktok.com short link resolves to."""
    if not isinstance(payload, list):
        return None
    for row in payload:
        is_row = isinstance(row, list) and len(row) > 2 and isinstance(row[2], dict)
        if is_row and row[2].get("subcategory") == "vmpost" and isinstance(row[1], str):
            return row[1]
    return None


async def fetch_metadata(url: str, settings: Settings) -> PostMetadata:
    """Caption and post identity, when yt-dlp cannot get them.

    yt-dlp's TikTok extractor breaks periodically — currently with "Unexpected
    response from webpage request" on every video. gallery-dl reads the same
    posts from a different code path, and the caption is the part that matters:
    it is usually where the ingredients are.
    """
    payload = await _dump_json(url, settings, TIMEOUT_METADATA)

    post = _first_post(payload)
    if post is None:
        # A short link resolves to a redirect row and nothing else. Follow it
        # once; a second redirect would be a loop, so do not recurse further.
        target = _redirect_target(payload)
        if target is None:
            raise GalleryDlError("no post metadata in gallery-dl output")
        payload = await _dump_json(target, settings, TIMEOUT_METADATA)
        post = _first_post(payload)
        if post is None:
            raise GalleryDlError("no post metadata after following the short link")
        url = target

    author = post.get("author")
    uploader = None
    if isinstance(author, dict):
        # uniqueId is the @handle; nickname is the display name.
        uploader = author.get("uniqueId") or author.get("nickname")

    # `desc` is TikTok's own field. `title` is gallery-dl's copy of it, so it is
    # a fallback rather than a different value.
    caption = post.get("desc") or post.get("title") or ""

    return PostMetadata(
        post_id=str(post.get("id") or ""),
        caption=str(caption),
        uploader=str(uploader) if uploader else None,
        webpage_url=url,
    )


async def download(url: str, destination: Path, settings: Settings) -> list[Path]:
    """Download a post's media into a flat directory."""
    destination.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        "gallery-dl",
        "--user-agent",
        settings.scraper_user_agent,
        "--dest",
        str(destination),
        "--directory",
        "",  # flat: no per-site subdirectory tree
        "--quiet",
        "--no-part",
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise GalleryDlError(f"timed out after {TIMEOUT}s") from None

    files = sorted(p for p in destination.rglob("*") if p.is_file())
    if process.returncode != 0 and not files:
        raise GalleryDlError(stderr.decode("utf-8", errors="replace")[:500] or "gallery-dl failed")
    return files
