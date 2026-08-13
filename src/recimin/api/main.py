"""FastAPI application factory."""

import logging
import sqlite3
from collections.abc import Callable

from fastapi import FastAPI

from recimin import __version__
from recimin.api.middleware import build_origin_guard
from recimin.api.routes import auth as auth_routes
from recimin.api.routes import recipes as recipe_routes
from recimin.api.routes import tokens as token_routes
from recimin.config import Settings, get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.db.repositories import jobs as jobs_repo
from recimin.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    db_factory: Callable[[], sqlite3.Connection] | None = None,
    migrate: bool = True,
) -> FastAPI:
    """Build the ASGI application.

    Passing settings and a db_factory explicitly keeps tests free of environment
    and filesystem coupling.
    """
    configure_logging()
    settings = settings or get_settings()
    factory = db_factory or (lambda: connect(settings.db_path))

    if migrate:
        bootstrap = factory()
        try:
            schema.migrate(bootstrap)
        finally:
            bootstrap.close()

    app = FastAPI(title="Recimin", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.db_factory = factory

    app.middleware("http")(build_origin_guard(settings.allowed_origin))

    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(recipe_routes.router, prefix="/api")
    app.include_router(token_routes.router, prefix="/api")

    @app.get("/health")
    def health() -> dict[str, object]:
        conn = factory()
        try:
            depth = jobs_repo.queue_depth(conn)
            db_ok = True
        except sqlite3.Error:
            depth = -1
            db_ok = False
        finally:
            conn.close()
        return {"status": "ok" if db_ok else "degraded", "version": __version__, "queue": depth}

    logger.info("api started", extra={"version": __version__, "data_dir": str(settings.data_dir)})
    return app


app = create_app()
