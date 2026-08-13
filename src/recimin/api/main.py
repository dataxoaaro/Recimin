"""FastAPI application factory.

Phase 0 exposes only /health. Routes arrive in Phase 2.
"""

import logging

from fastapi import FastAPI

from recimin import __version__
from recimin.config import Settings, get_settings
from recimin.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application.

    Passing settings explicitly keeps tests free of environment coupling.
    """
    configure_logging()
    settings = settings or get_settings()

    app = FastAPI(title="Recimin", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    logger.info("api started", extra={"version": __version__, "data_dir": str(settings.data_dir)})
    return app


app = create_app()
