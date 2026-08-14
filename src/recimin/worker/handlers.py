"""Platform dispatch and persistence.

Phase 6 implements the web path. Social extractors land in Phase 7 behind the
same signature.
"""

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from recimin.config import Settings
from recimin.db.models import CaptionGate, Job, JobStage, RecipeStatus, SourcePlatform
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import media as media_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories.ingredients import IngredientDraft
from recimin.db.repositories.recipes import RecipeDraft
from recimin.importer import caption as caption_gate
from recimin.importer import social, web
from recimin.importer.ingredients import alternative_positions
from recimin.importer.ingredients import parse as parse_ingredient
from recimin.importer.normalise import NormalisedRecipe
from recimin.importer.urls import Classified, Platform, UrlRejected, classify
from recimin.llm import extract as llm_extract
from recimin.media import frames
from recimin.worker.loop import NonRetryable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Extraction:
    """What an extractor produced, and how far to trust it.

    `confidence` is None when the recipe came from schema.org structured data,
    which the site authored and we parsed deterministically. Otherwise it is the
    model's own verdict. It used to be logged and discarded, which left nothing
    to distinguish a clean parse from a guess off a blurry video frame.
    """

    recipe: NormalisedRecipe
    ingredient_rows: list[dict[str, object]] | None = None
    media_ids: list[int] = field(default_factory=list)
    confidence: str | None = None


def status_for(confidence: str | None) -> RecipeStatus:
    """Decide whether an extraction needs a human to look at it.

    Everything used to be written as a draft, on the reasoning that extraction
    is probabilistic and a human would confirm it on a review screen. That
    screen was never built, so draft became a state with no exit: every import
    wore the badge forever and it stopped carrying information.

    `None` means the recipe came from schema.org structured data — authored by
    the site, parsed deterministically, not a guess. Otherwise it is the
    model's own verdict on its extraction, which is the signal actually worth
    surfacing: only medium and low get flagged.
    """
    if confidence is None or confidence == "high":
        return RecipeStatus.PUBLISHED
    return RecipeStatus.DRAFT


def persist(
    conn: sqlite3.Connection,
    recipe: NormalisedRecipe,
    classified: Classified,
    *,
    source_url: str,
    ingredient_rows: list[dict[str, object]] | None = None,
    confidence: str | None = None,
) -> int:
    """Write an extracted recipe, flagged for review only if it warrants it."""
    from urllib.parse import urlsplit

    from recimin.db.clock import now

    links = alternative_positions(recipe.ingredients)

    return recipes_repo.create(
        conn,
        RecipeDraft(
            title=recipe.title,
            instructions_md=recipe.instructions_md,
            description=recipe.description,
            servings=recipe.servings,
            yield_text=recipe.yield_text,
            total_time_minutes=recipe.total_time_minutes,
            language=recipe.language,
            status=status_for(confidence),
            source_url=source_url,
            source_url_normalised=classified.normalised,
            source_site=urlsplit(classified.normalised).hostname,
            source_author=recipe.author,
            source_title=recipe.title,
            source_platform=SourcePlatform(str(classified.platform)),
            imported_at=now(),
        ),
        ingredient_lines=(
            [IngredientDraft(**row) for row in ingredient_rows]  # type: ignore[arg-type]
            if ingredient_rows is not None
            else [
                IngredientDraft(
                    raw_text=line,
                    qty=parsed.qty,
                    unit=parsed.unit,
                    item=parsed.item,
                    note=parsed.note,
                    alternative_of=links.get(position),
                )
                for position, line in enumerate(recipe.ingredients)
                if (parsed := parse_ingredient(line)) is not None
            ]
        ),
    )


async def _llm_from_page(
    job: Job, error: web.NoRecipeFound, settings: Settings
) -> Extraction | None:
    """Last resort for a page with no structured data."""
    if not (settings.llm_enabled and settings.openrouter_api_key and len(error.page_text) > 200):
        return None

    try:
        extracted = await llm_extract.from_web_text(error.page_text, settings)
    except (llm_extract.LlmUnavailable, llm_extract.LlmRefused) as llm_error:
        logger.info(
            "llm web fallback failed",
            extra={"job_id": job.id, "error": str(llm_error)[:200]},
        )
        return None

    recipe, rows = llm_extract.to_normalised(extracted)
    if not recipe.is_usable:
        return None

    logger.info(
        "llm web fallback supplied the recipe",
        extra={"job_id": job.id, "confidence": extracted.confidence},
    )
    return Extraction(recipe, ingredient_rows=rows, confidence=extracted.confidence)


async def _import_social(
    conn: sqlite3.Connection, job: Job, classified: Classified, settings: Settings
) -> Extraction:
    """Fetch a social post: caption first, then media, then an extraction."""
    try:
        metadata = await social.fetch_metadata(classified, settings)
    except social.SocialFetchFailed as error:
        if error.needs_update:
            # The extractor is stale rather than the URL bad. Try one in-place
            # upgrade; if that does not help, a human has to look.
            from recimin.importer import ytdlp

            if await ytdlp.self_update():
                metadata = await social.fetch_metadata(classified, settings)
            else:
                raise NonRetryable(f"yt-dlp needs updating: {error}") from None
        else:
            raise

    gate = (
        CaptionGate.HIT if caption_gate.looks_like_a_recipe(metadata.caption) else CaptionGate.MISS
    )
    jobs_repo.set_caption_gate(conn, job.id, gate)
    logger.info(
        "caption gate",
        extra={"job_id": job.id, "verdict": str(gate), "caption_chars": len(metadata.caption)},
    )

    # The gate decides whether extraction is needed, never whether media is
    # kept: the archive is the point, and the source post may be deleted.
    jobs_repo.set_stage(conn, job.id, JobStage.MEDIA)
    files: list[Path] = []
    rows: list[dict[str, object]] | None = None
    # A caption-only draft is a guess by construction, so it stays flagged even
    # when the model never ran. "low" rather than None, which would claim the
    # certainty of structured data.
    confidence = "low"
    try:
        try:
            files, subtitles = await social.download_media(classified, settings)
        except social.SocialFetchFailed as error:
            if error.needs_update:
                raise NonRetryable(f"yt-dlp needs updating: {error}") from None
            raise

        # A video cannot render in an <img>, so a clip-only post would show an
        # empty card. Generate a poster before storing, and put it first so it
        # becomes the hero.
        video_file = next((f for f in files if f.suffix.lower() in social.VIDEO_SUFFIXES), None)
        if video_file is not None and not any(
            f.suffix.lower() in social.IMAGE_SUFFIXES for f in files
        ):
            poster = await frames.extract_poster(
                video_file, video_file.with_name(f"{video_file.stem}_poster.jpg")
            )
            if poster is not None:
                files = [poster, *files]

        media_ids = social.store_media(
            conn, files, settings=settings, source_url=classified.normalised
        )

        # Extraction runs before cleanup: the frames come from the video file,
        # which lives in the temp directory until the finally below.
        recipe = social.draft_from_caption(metadata, classified, subtitles)

        if settings.llm_enabled and settings.openrouter_api_key:
            jobs_repo.set_stage(conn, job.id, JobStage.EXTRACT)
            video = next((f for f in files if f.suffix.lower() in social.VIDEO_SUFFIXES), None)
            try:
                extracted = await llm_extract.from_social(
                    caption=metadata.caption,
                    transcript=subtitles,
                    video=video,
                    settings=settings,
                )
                recipe, rows = llm_extract.to_normalised(extracted)
                confidence = extracted.confidence
                if recipe.language == "en" and metadata.caption:
                    # Trust our own detector over the model on this one field.
                    recipe.language = social.draft_from_caption(metadata, classified, "").language
                logger.info(
                    "llm extraction applied",
                    extra={
                        "job_id": job.id,
                        "ingredients": len(rows),
                        "confidence": extracted.confidence,
                    },
                )
            except (llm_extract.LlmUnavailable, llm_extract.LlmRefused) as error:
                # A caption-only draft is still worth having: the media is
                # archived and the user can finish it by hand.
                logger.warning(
                    "llm extraction skipped",
                    extra={"job_id": job.id, "error": str(error)[:200]},
                )
    finally:
        if files:
            await social.cleanup(files)

    return Extraction(recipe, ingredient_rows=rows, media_ids=media_ids, confidence=confidence)


async def handle_import(conn: sqlite3.Connection, job: Job, settings: Settings) -> int | None:
    """Route a job to its extractor and return the resulting recipe id."""
    jobs_repo.set_stage(conn, job.id, JobStage.RESOLVE)

    try:
        classified = classify(job.input_url)
    except UrlRejected as rejected:
        raise NonRetryable(str(rejected)) from None

    # Deduplicate again here: a short link's real target is only known after
    # the fetch, and a second job may have been queued while this one waited.
    existing = recipes_repo.get_by_normalised_url(conn, classified.normalised)
    if existing is not None:
        logger.info("already imported", extra={"job_id": job.id, "recipe_id": existing.id})
        return existing.id

    jobs_repo.set_stage(conn, job.id, JobStage.FETCH)
    if classified.platform is Platform.WEB:
        try:
            # httpx is synchronous here; keep the event loop free for the API.
            parsed = await asyncio.to_thread(web.extract, classified.normalised, settings)
            # No confidence: schema.org is the site's own structured data, read
            # deterministically. Nothing was inferred, so nothing needs review.
            extraction = Extraction(parsed)
        except web.NoRecipeFound as error:
            # Structured data found nothing. The page may still be a recipe
            # written as prose, so spend one LLM call on the readable text
            # before giving up — but only if there is text worth sending.
            fallback = await _llm_from_page(job, error, settings)
            if fallback is None:
                raise NonRetryable(str(error)) from None
            extraction = fallback
    else:
        extraction = await _import_social(conn, job, classified, settings)

    jobs_repo.set_stage(conn, job.id, JobStage.PERSIST)
    recipe_id = persist(
        conn,
        extraction.recipe,
        classified,
        source_url=job.input_url,
        ingredient_rows=extraction.ingredient_rows,
        confidence=extraction.confidence,
    )
    for media_id in extraction.media_ids:
        media_repo.attach_to_recipe(conn, media_id, recipe_id)
    if extraction.media_ids:
        recipes_repo.update(conn, recipe_id, hero_media_id=extraction.media_ids[0])
    logger.info(
        "import complete",
        extra={
            "job_id": job.id,
            "recipe_id": recipe_id,
            "title": extraction.recipe.title,
            "confidence": extraction.confidence,
            "status": str(status_for(extraction.confidence)),
        },
    )
    return recipe_id
