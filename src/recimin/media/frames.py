"""Frame and audio extraction with ffmpeg.

Fixed-interval sampling, not scene detection. Instagram's default text-card
duration is 5 seconds and creator guidance says 2 seconds minimum, so an even
sample at or below 2s catches every ingredient card — while scene detection
forces a full decode and yields an unpredictable count.

768x1344 is deliberate: OpenAI's mini models cap at 1,536 image patches, and
that size lands at 1,008. A full 1080x1920 frame is 2,040 and triggers a
downscale we do not control.
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FRAME_COUNT = 12
FRAME_WIDTH = 768
JPEG_QUALITY = 2  # ffmpeg -q:v scale is 2-31, lower is better
TIMEOUT = 300


class FfmpegError(Exception):
    """ffmpeg failed."""


async def _run(args: list[str], timeout: int = TIMEOUT) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise FfmpegError(f"timed out after {timeout}s") from None
    if process.returncode != 0:
        raise FfmpegError(stderr.decode("utf-8", errors="replace")[:400])
    return stdout


async def duration_seconds(video: Path) -> float:
    """Clip length, needed to spread frames across the whole video."""
    out = await _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(video),
        ],
        timeout=60,
    )
    try:
        return float(out.decode().strip())
    except ValueError as error:
        raise FfmpegError(f"unreadable duration: {out!r}") from error


async def extract_frames(video: Path, destination: Path, *, count: int = FRAME_COUNT) -> list[Path]:
    """Sample frames evenly across a clip.

    The rate is count/duration rather than `-frames:v count`, because the
    latter takes the *first* N matches and bunches them at the start.

    mpdecimate is placed AFTER fps= so it dedupes the sampled frames rather
    than all ~1,800 of them.
    """
    destination.mkdir(parents=True, exist_ok=True)
    duration = await duration_seconds(video)
    if duration <= 0:
        raise FfmpegError("zero-length video")

    await _run(
        [
            "ffmpeg",
            "-nostdin",
            "-i",
            str(video),
            "-vf",
            f"fps={count}/{duration:.3f},mpdecimate=hi=768:lo=320:frac=0.33,scale={FRAME_WIDTH}:-2",
            "-fps_mode",
            "vfr",
            "-q:v",
            str(JPEG_QUALITY),
            str(destination / "frame_%03d.jpg"),
        ]
    )
    frames = sorted(destination.glob("frame_*.jpg"))
    logger.info(
        "frames extracted",
        extra={"video": video.name, "duration_s": round(duration, 1), "frames": len(frames)},
    )
    return frames


async def extract_audio(video: Path, destination: Path) -> Path | None:
    """Pull a 16 kHz mono track, or None when the clip is silent.

    Gemini accepts audio natively at 32 tokens per second — a 60-second clip is
    1,920 tokens, cheaper per minute than any dedicated ASR API.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        await _run(
            [
                "ffmpeg",
                "-nostdin",
                "-i",
                str(video),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                str(destination),
            ]
        )
    except FfmpegError as error:
        logger.info("no audio track", extra={"video": video.name, "error": str(error)[:120]})
        return None
    return destination if destination.is_file() and destination.stat().st_size > 0 else None


async def extract_poster(video: Path, destination: Path) -> Path | None:
    """Grab a single frame to use as the recipe's hero image.

    A video cannot be rendered in an <img>, so a recipe whose only media is a
    clip would show an empty card. Taken at 1s rather than 0s: the first frame
    of a reel is very often black or a title card.

    Generated locally rather than downloaded, following IGStore — the platform
    thumbnail is another expiring URL, and we already have the bytes.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        seek = "1"
        duration = await duration_seconds(video)
        if duration < 2:
            seek = "0"
        await _run(
            [
                "ffmpeg",
                "-nostdin",
                "-ss",
                seek,
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={FRAME_WIDTH}:-2",
                "-q:v",
                str(JPEG_QUALITY),
                str(destination),
            ],
            timeout=60,
        )
    except FfmpegError as error:
        logger.warning("poster extraction failed", extra={"error": str(error)[:200]})
        return None
    return destination if destination.is_file() and destination.stat().st_size > 0 else None
