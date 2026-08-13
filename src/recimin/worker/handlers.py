"""Platform dispatch and persistence.

Phase 6 implements the web path. Social extractors land in Phase 7 behind the
same signature.
"""

import asyncio
import logging
import sqlite3

from recimin.config import Settings
from recimin.db.models import Job, JobStage, RecipeStatus, SourcePlatform
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories.ingredients import IngredientDraft
from recimin.db.repositories.recipes import RecipeDraft
from recimin.importer import web
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

    if classified.platform is not Platform.WEB:
        raise NonRetryable(f"{classified.platform} import is not implemented yet")

    jobs_repo.set_stage(conn, job.id, JobStage.FETCH)
    try:
        # httpx is synchronous here; keep the event loop free for the API.
        recipe = await asyncio.to_thread(web.extract, classified.normalised, settings)
    except web.NoRecipeFound as error:
        raise NonRetryable(str(error)) from None

    jobs_repo.set_stage(conn, job.id, JobStage.PERSIST)
    recipe_id = persist(conn, recipe, classified, source_url=job.input_url)
    logger.info(
        "import complete",
        extra={"job_id": job.id, "recipe_id": recipe_id, "title": recipe.title},
    )
    return recipe_id
