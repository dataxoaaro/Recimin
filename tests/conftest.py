"""Shared test fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recimin.api.main import create_app
from recimin.config import Settings

TEST_JWT_SECRET = "x" * 32
TEST_SITE_PASSWORD = "test-site-password"

_ENV_KEYS = (
    "JWT_SECRET",
    "SITE_PASSWORD",
    "DATA_DIR",
    "ALLOWED_ORIGIN",
    "SCRAPER_USER_AGENT",
    "RENDER_SERVICE_URL",
    "OPENROUTER_API_KEY",
    "LLM_ENABLED",
    "MAX_MEDIA_BYTES",
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from the developer's .env and shell environment.

    Without this, a populated .env in the repo root silently satisfies required
    settings and the "missing secret must raise" tests pass vacuously.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at a throwaway data directory."""
    return Settings(
        jwt_secret=TEST_JWT_SECRET,
        site_password=TEST_SITE_PASSWORD,
        data_dir=tmp_path,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient bound to an app built from the test settings."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
