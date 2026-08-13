"""Platform dispatch and persistence.

Phase 6 implements the web path. Social extractors land in Phase 7 behind the
same signature.
"""

import asyncio
import logging
import sqlite3
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
from recimin.importer.normalise import NormalisedRecipe
from recimin.importer.urls import Classified, Platform, UrlRejected, classify
from recimin.worker.loop import NonRetryable

logger = logging.getLogger(__name__)


def persist(
    conn: sqlite3.Connection,
    recipe: NormalisedRecipe,
    classified: Classified,
    *,
    source_url: str,
) -> int:
    """Write an extracted recipe as a draft.

    Always a draft: extraction is probabilistic, and a human confirms it on the
    review screen before it joins the library proper.
    """
    from urllib.parse import urlsplit

    from recimin.db.clock import now

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
            status=RecipeStatus.DRAFT,
            source_url=source_url,
            source_url_normalised=classified.normalised,
            source_site=urlsplit(classified.normalised).hostname,
            source_author=recipe.author,
            source_title=recipe.title,
            source_platform=SourcePlatform(str(classified.platform)),
            imported_at=now(),
        ),
        ingredient_lines=[IngredientDraft(raw_text=line) for line in recipe.ingredients],
    )


async def _import_social(
    conn: sqlite3.Connection, job: Job, classified: Classified, settings: Settings
) -> tuple[NormalisedRecipe, list[int]]:
    """Fetch a social post: caption first, then media, then a draft."""
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
    try:
        files, subtitles = await social.download_media(classified, settings)
        media_ids = social.store_media(
            conn, files, settings=settings, source_url=classified.normalised
        )
    except social.SocialFetchFailed as error:
        if error.needs_update:
            raise NonRetryable(f"yt-dlp needs updating: {error}") from None
        raise
    finally:
        if files:
            await social.cleanup(files)

    return social.draft_from_caption(metadata, classified, subtitles), media_ids


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
            recipe = await asyncio.to_thread(web.extract, classified.normalised, settings)
        except web.NoRecipeFound as error:
            raise NonRetryable(str(error)) from None
        media_ids: list[int] = []
    else:
        recipe, media_ids = await _import_social(conn, job, classified, settings)

    jobs_repo.set_stage(conn, job.id, JobStage.PERSIST)
    recipe_id = persist(conn, recipe, classified, source_url=job.input_url)
    for media_id in media_ids:
        media_repo.attach_to_recipe(conn, media_id, recipe_id)
    if media_ids:
        recipes_repo.update(conn, recipe_id, hero_media_id=media_ids[0])
    logger.info(
        "import complete",
        extra={"job_id": job.id, "recipe_id": recipe_id, "title": recipe.title},
    )
    return recipe_id
