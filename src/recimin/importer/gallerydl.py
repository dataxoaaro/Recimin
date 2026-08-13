"""gallery-dl adapter.

Exists for exactly one reason: TikTok photo-slideshow posts. yt-dlp's TikTok
regex matches only /video/ and the extractor has no imagePost handling, so a
/photo/ URL falls through to the generic extractor and fails. gallery-dl
matches /(?:phot|vide)o/ and iterates imagePost.images.

It also serves as the TikTok fallback when yt-dlp breaks, which it does a few
times a year.
"""

import asyncio
import logging
from pathlib import Path

from recimin.config import Settings

logger = logging.getLogger(__name__)

TIMEOUT = 600


class GalleryDlError(Exception):
    """gallery-dl failed."""


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
