"""FastAPI application factory."""

import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from recimin import __version__
from recimin.api import ratelimit
from recimin.api.middleware import build_origin_guard
from recimin.api.routes import auth as auth_routes
from recimin.api.routes import imports as import_routes
from recimin.api.routes import media as media_routes
from recimin.api.routes import push as push_routes
from recimin.api.routes import recipes as recipe_routes
from recimin.api.routes import tokens as token_routes
from recimin.config import Settings, get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.db.repositories import jobs as jobs_repo
from recimin.logging import configure_logging

logger = logging.getLogger(__name__)


SPA_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"

# Everything the SPA route serves has a stable name — index.html, sw.js,
# manifest.webmanifest, the icons — so a deploy replaces the contents behind an
# unchanged URL. Without a Cache-Control header Cloudflare applies its own
# default of four hours, which was observed serving a superseded icon.svg with
# `cf-cache-status: HIT` half an hour after a deploy. On sw.js that is worse
# than cosmetic: browsers only bypass the HTTP cache for a service worker when
# max-age exceeds 86400, so an installed PWA keeps running the old build.
#
# `no-cache` still caches — it requires revalidation first, so the common case
# is a cheap 304 rather than a refetch. Hashed assets under /assets are the
# opposite case and are handled by _ImmutableStatic.
_NO_CACHE = {"Cache-Control": "no-cache"}


class _ImmutableStatic(StaticFiles):
    """Static files whose names carry a content hash, so they never change.

    Vite fingerprints everything under /assets, which makes a year-long
    immutable cache both safe and the only way to avoid revalidating every
    asset on every navigation.
    """

    def file_response(self, *args: object, **kwargs: object) -> Response:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_spa(app: FastAPI) -> None:
    """Serve the built SPA, falling back to index.html for client-side routes.

    Absent in development, where Vite serves the frontend and proxies /api here.
    """
    if not (SPA_DIR / "index.html").is_file():
        logger.info("spa not built, serving api only", extra={"dir": str(SPA_DIR)})
        return

    app.mount("/assets", _ImmutableStatic(directory=SPA_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = SPA_DIR / path
        # Serve a real file when one exists (sw.js, manifest, icon), otherwise
        # hand back the shell so deep links like /settings work on reload.
        if path and candidate.is_file() and SPA_DIR in candidate.resolve().parents:
            return FileResponse(candidate, headers=_NO_CACHE)
        return FileResponse(SPA_DIR / "index.html", headers=_NO_CACHE)


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

    bootstrap = factory()
    try:
        if migrate:
            schema.migrate(bootstrap)
        # Operational state, not data model — created here rather than by a
        # migration, and here rather than per login request.
        ratelimit.ensure_table(bootstrap)
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
    app.include_router(import_routes.router, prefix="/api")
    app.include_router(media_routes.router, prefix="/api")
    app.include_router(push_routes.router, prefix="/api")
    app.include_router(recipe_routes.router, prefix="/api")
    app.include_router(token_routes.router, prefix="/api")

    @app.get("/health")
    def health(response: Response) -> dict[str, object]:
        conn = factory()
        try:
            depth = jobs_repo.queue_depth(conn)
            db_ok = True
        except sqlite3.Error:
            depth = -1
            db_ok = False
        finally:
            conn.close()

        if not db_ok:
            # 503, not 200-with-a-sad-word. Docker's healthcheck is `curl -fsS`,
            # which only fails on a >=400 status, so returning 200 here means a
            # container with an unreachable database reports itself healthy —
            # precisely the failure a healthcheck exists to catch.
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {"status": "ok" if db_ok else "degraded", "version": __version__, "queue": depth}

    # Registered last: it is a catch-all, and FastAPI matches in declaration
    # order, so mounting it earlier silently shadows /health and every /api route.
    _mount_spa(app)

    logger.info("api started", extra={"version": __version__, "data_dir": str(settings.data_dir)})
    return app


app = create_app()
