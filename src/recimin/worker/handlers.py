"""Platform dispatch.

Phase 5 ships the routing and a stub for each platform. Real extractors land in
Phase 6 (web) and Phase 7 (social); they slot in behind this same signature.
"""

import logging
import sqlite3

from recimin.config import Settings
from recimin.db.models import Job, JobStage
from recimin.db.repositories import jobs as jobs_repo
from recimin.importer.urls import Platform, UrlRejected, classify
from recimin.worker.loop import NonRetryable

logger = logging.getLogger(__name__)


async def handle_import(conn: sqlite3.Connection, job: Job, settings: Settings) -> int | None:
    """Route a job to its extractor and return the resulting recipe id."""
    jobs_repo.set_stage(conn, job.id, JobStage.RESOLVE)

    try:
        classified = classify(job.input_url)
    except UrlRejected as rejected:
        raise NonRetryable(str(rejected)) from None

    if classified.platform is Platform.WEB:
        raise NonRetryable("Web import is not implemented yet")
    raise NonRetryable(f"{classified.platform} import is not implemented yet")
