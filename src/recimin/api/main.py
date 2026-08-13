"""FastAPI application factory."""

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from recimin import __version__
from recimin.api.middleware import build_origin_guard
from recimin.api.routes import auth as auth_routes
from recimin.api.routes import media as media_routes
from recimin.api.routes import recipes as recipe_routes
from recimin.api.routes import tokens as token_routes
from recimin.config import Settings, get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.db.repositories import jobs as jobs_repo
from recimin.logging import configure_logging

logger = logging.getLogger(__name__)


SPA_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def _mount_spa(app: FastAPI) -> None:
    """Serve the built SPA, falling back to index.html for client-side routes.

    Absent in development, where Vite serves the frontend and proxies /api here.
    """
    if not (SPA_DIR / "index.html").is_file():
        logger.info("spa not built, serving api only", extra={"dir": str(SPA_DIR)})
        return

    app.mount("/assets", StaticFiles(directory=SPA_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = SPA_DIR / path
        # Serve a real file when one exists (sw.js, manifest, icon), otherwise
        # hand back the shell so deep links like /settings work on reload.
        if path and candidate.is_file() and SPA_DIR in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(SPA_DIR / "index.html")


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

    # No interactive docs and no schema endpoint: this is a private household
    # app, and publishing its API surface buys nothing.
    app = FastAPI(
        title="Recimin",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.db_factory = factory

    app.middleware("http")(build_origin_guard(settings.allowed_origin))

    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(media_routes.router, prefix="/api")
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

    # Registered last: it is a catch-all, and FastAPI matches in declaration
    # order, so mounting it earlier silently shadows /health and every /api route.
    _mount_spa(app)

    logger.info("api started", extra={"version": __version__, "data_dir": str(settings.data_dir)})
    return app


app = create_app()
