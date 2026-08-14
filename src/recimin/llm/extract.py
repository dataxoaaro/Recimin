"""Extraction orchestration.

One LLM call per import, at most. The request carries the caption, the
subtitle transcript, and frames sampled from the video.

The raw video is never sent. Gemini samples video at a fixed 1fps and charges
70 tokens per video frame against 1,120 for an extracted image, and
media_resolution cannot be overridden through OpenRouter. For reading
burned-in ingredient cards, per-frame resolution is the whole game.
"""

import logging
import tempfile
from pathlib import Path

from recimin.config import Settings
from recimin.importer.ingredients import parse_lines
from recimin.importer.normalise import NormalisedRecipe
from recimin.llm import prompts
from recimin.llm.client import LlmRefused, LlmUnavailable, extract
from recimin.llm.schema import SUGGESTED_TAG_SET, ExtractedRecipe
from recimin.media import frames as frames_mod

logger = logging.getLogger(__name__)

__all__ = ["LlmRefused", "LlmUnavailable", "from_social", "from_web_text", "to_normalised"]


def to_normalised(extracted: ExtractedRecipe) -> tuple[NormalisedRecipe, list[dict[str, object]]]:
    """Convert a model response into a persistable recipe plus its ingredients.

    Alternatives are re-derived here rather than trusted from the model: the
    "TAI" suffix is a deterministic signal and a rule beats a hope.
    """
    raw_lines = [line.raw_text for line in extracted.ingredients]

    ingredient_rows: list[dict[str, object]] = []
    for line, (fallback, link) in zip(extracted.ingredients, parse_lines(raw_lines), strict=True):
        ingredient_rows.append(
            {
                "raw_text": line.raw_text,
                "original_text": line.original_text,
                # Prefer the model's parse, fall back to the deterministic one.
                "qty": line.qty if line.qty is not None else fallback.qty,
                "unit": line.unit or fallback.unit,
                "item": line.item or fallback.item,
                "note": line.note or fallback.note,
                "group_label": line.group_label,
                "alternative_of": link if link is not None else line.alternative_of,
            }
        )

    recipe = NormalisedRecipe(
        title=extracted.title,
        ingredients=raw_lines,
        instructions_md=extracted.instructions_md,
        servings=extracted.servings,
        yield_text=extracted.yield_text,
        total_time_minutes=extracted.total_time_minutes,
        description=extracted.description,
        language=extracted.language,
        category=extracted.category,
        # The prompt says "omit rather than invent", but that is a hope, not a
        # rule. Filtering to the vocabulary here is the rule.
        tags=[tag for raw in extracted.tags if (tag := raw.strip().lower()) in SUGGESTED_TAG_SET],
    )
    return recipe, ingredient_rows


async def from_web_text(page_text: str, settings: Settings) -> ExtractedRecipe:
    """Last-resort extraction from a page with no structured data."""
    recipe, _ = await extract(
        settings,
        system=prompts.WEB_FALLBACK,
        text=prompts.user_message("", "", page_text),
    )
    return recipe


async def from_social(
    *,
    caption: str,
    transcript: str,
    video: Path | None,
    settings: Settings,
) -> ExtractedRecipe:
    """Extract from a social post: caption, sampled frames and audio."""
    workdir = Path(tempfile.mkdtemp(prefix="recimin-frames-"))
    frame_paths: list[Path] = []
    try:
        if video is not None and video.is_file():
            try:
                frame_paths = await frames_mod.extract_frames(video, workdir)
            except frames_mod.FfmpegError as error:
                # Frames are the best signal but not the only one; a caption
                # plus transcript still beats failing the import outright.
                logger.warning("frame extraction failed", extra={"error": str(error)[:200]})

        recipe, _ = await extract(
            settings,
            system=prompts.SOCIAL_EXTRACTION,
            text=prompts.user_message(caption, transcript, ""),
            images=frame_paths,
        )
        return recipe
    finally:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
