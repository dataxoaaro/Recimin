"""yt-dlp adapter.

Invoked as a subprocess rather than imported, following IGStore: the tool
changes fast, and a subprocess boundary means a broken release cannot take the
worker's interpreter with it.

Three rules from Appendix A, all of which fail silently if broken:

  1. Always pass a current Chrome User-Agent. TikTok rejects yt-dlp's default.
     Measured back to back, same URL and IP: 0/6 with the default UA, 12/12
     with Chrome.
  2. Read `description`, never `title`. Instagram's title is literally
     "Video by <username>"; TikTok truncates its title at 72 characters.
  3. The install must be `yt-dlp[default,curl-cffi]` with a hyphen. Without
     impersonation the Instagram GraphQL path is skipped entirely.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from recimin.config import Settings

logger = logging.getLogger(__name__)

TIMEOUT_METADATA = 60
TIMEOUT_DOWNLOAD = 900

# yt-dlp signals "my extractor is out of date" through exit 100 or this text.
# IGStore surfaces exactly the same markers.
# Signatures of an extractor that has fallen behind the site rather than a bad
# URL. "unexpected response from webpage request" is TikTok's current one.
#
# "Confirm you are on the latest version using yt-dlp -U" is NOT a marker:
# yt-dlp appends it to nearly every extractor error, including a private
# Instagram post, so matching on it sent a login wall into the self-update
# path and parked the job as "yt-dlp needs updating" when yt-dlp was current.
NEEDS_UPDATE_MARKERS = (
    "unable to extract",
    "unsupported url",
    "no video formats",
    "unexpected response",
)
NEEDS_UPDATE_EXIT = 100

# The post exists but the platform will not serve it to a logged-out visitor:
# private, age-gated, region-locked, or the IP is being rate-limited. Retrying
# only spends per-IP tolerance, and no version of yt-dlp changes the answer.
# "empty media response" is Instagram's phrasing for the login wall; the
# error text goes on to suggest --cookies, which this project never uses.
INACCESSIBLE_MARKERS = (
    "empty media response",
    "login required",
    "log in",
    "rate-limit",
    "requested content is not available",
    "private video",
    "this video is private",
)


class YtDlpError(Exception):
    """yt-dlp failed.

    needs_update: the extractor is stale; an upgrade may fix it.
    inaccessible: the platform refused to serve the post; nothing will fix it.
    The two are exclusive.
    """

    def __init__(
        self, message: str, *, needs_update: bool = False, inaccessible: bool = False
    ) -> None:
        super().__init__(message)
        self.needs_update = needs_update
        self.inaccessible = inaccessible


@dataclass(frozen=True, slots=True)
class PostMetadata:
    """What a social post tells us before anything is downloaded."""

    post_id: str
    caption: str
    uploader: str | None
    webpage_url: str


def base_args(settings: Settings) -> list[str]:
    """Arguments shared by every invocation."""
    args = [
        "yt-dlp",
        "--user-agent",
        settings.scraper_user_agent,
        "--no-warnings",
        "--no-progress",
        "--no-playlist-reverse",
        "--socket-timeout",
        "20",
        "--retries",
        "2",
    ]
    # Without this the Chrome User-Agent above goes out over yt-dlp's own TLS
    # fingerprint, which is a mismatch a bot check can read directly. The worker
    # image installs curl-cffi for exactly this and fails to build if no
    # impersonate target is available; an empty setting omits the flag, for a
    # yt-dlp built without the extra.
    if settings.scraper_impersonate:
        args += ["--impersonate", settings.scraper_impersonate]
    return args


async def _run(args: list[str], timeout: int) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise YtDlpError(f"timed out after {timeout}s") from None
    return process.returncode or 0, stdout, stderr


def _classify_failure(code: int, stderr: bytes) -> YtDlpError:
    text = stderr.decode("utf-8", errors="replace").strip()
    lowered = text.lower()
    # Checked first: a login wall is a fact about the post, and it wins over
    # any staleness marker that might also appear in the same message.
    inaccessible = any(marker in lowered for marker in INACCESSIBLE_MARKERS)
    needs_update = not inaccessible and (
        code == NEEDS_UPDATE_EXIT or any(marker in lowered for marker in NEEDS_UPDATE_MARKERS)
    )
    return YtDlpError(
        text[:500] or f"exit {code}", needs_update=needs_update, inaccessible=inaccessible
    )


async def fetch_metadata(url: str, settings: Settings) -> PostMetadata:
    """One metadata request, no bytes downloaded.

    This is what the caption gate runs on: if the caption already contains the
    recipe, nothing else needs to happen.
    """
    code, stdout, stderr = await _run(
        [*base_args(settings), "--dump-single-json", "--skip-download", url],
        TIMEOUT_METADATA,
    )
    if code != 0 or not stdout.strip():
        raise _classify_failure(code, stderr)

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise YtDlpError(f"unparseable metadata: {error}") from error

    return PostMetadata(
        post_id=str(data.get("id") or ""),
        # NEVER data["title"]: Instagram returns "Video by <username>".
        caption=str(data.get("description") or ""),
        # Order matters. On Instagram `uploader_id` is the numeric account id
        # (644361185) while `channel` is the handle (kinuskikissa) — attribution
        # should read "@kinuskikissa", not a number.
        uploader=data.get("channel") or data.get("uploader") or data.get("uploader_id"),
        # The canonical URL, which for a short link is the redirect target —
        # dedupe runs on this.
        webpage_url=str(data.get("webpage_url") or url),
    )


async def download(url: str, destination: Path, settings: Settings) -> list[Path]:
    """Download a post's media into a directory. Returns the files written."""
    destination.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await _run(
        [
            *base_args(settings),
            "--no-part",
            "--output",
            str(destination / "%(id)s.%(ext)s"),
            # TikTok publishes its own auto-captions; free, and better than ASR.
            "--write-auto-subs",
            "--sub-langs",
            "all",
            url,
        ],
        TIMEOUT_DOWNLOAD,
    )
    files = sorted(p for p in destination.iterdir() if p.is_file())
    if code != 0 and not files:
        raise _classify_failure(code, stderr)
    if code != 0:
        logger.warning(
            "yt-dlp reported an error but produced files",
            extra={"url": url, "files": len(files)},
        )
    return files


# The same install the worker image runs, so an upgrade lands where the
# `yt-dlp` on PATH actually lives: system python, not the app venv. The venv
# has no pip at all (uv builds it), which is why `python -m pip` failed on
# every production attempt with "No module named pip" and the self-update
# path had never once run.
SELF_UPDATE_ARGS = (
    "uv",
    "pip",
    "install",
    "--system",
    "--no-cache",
    "--pre",
    "--upgrade",
    "yt-dlp[default,curl-cffi]",
)
TIMEOUT_SELF_UPDATE = 300


async def self_update() -> bool:
    """Attempt an in-place upgrade after a needs-update signal.

    Stable went 84 days without a release in 2026 and left Instagram broken for
    weeks, so this tracks pre-releases. Note that `yt-dlp --update` refuses for
    pip installs *and misleadingly reports success*, which is why this shells
    out to the installer instead.
    """
    try:
        code, _, stderr = await _run(list(SELF_UPDATE_ARGS), TIMEOUT_SELF_UPDATE)
    except (FileNotFoundError, YtDlpError) as error:
        logger.warning("yt-dlp self-update failed", extra={"error": str(error)})
        return False
    if code != 0:
        logger.warning("yt-dlp self-update failed", extra={"stderr": stderr[:300].decode()})
        return False
    logger.info("yt-dlp updated")
    return True
