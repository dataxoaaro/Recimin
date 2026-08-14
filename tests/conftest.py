"""Shared test fixtures."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recimin.api.main import create_app
from recimin.config import Settings
from recimin.db import schema
from recimin.db.connection import connect

TEST_JWT_SECRET = "x" * 32
TEST_SITE_PASSWORD = "test-site-password"
TEST_EMAIL = "aaro@example.fi"
TEST_PASSWORD = "correct-horse-battery"

_ENV_KEYS = (
    "JWT_SECRET",
    "SITE_PASSWORD",
    "DATA_DIR",
    "ALLOWED_ORIGIN",
    "SCRAPER_USER_AGENT",
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
def db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A migrated database on disk, shared with the app under test."""
    conn = connect(tmp_path / "recimin.db")
    schema.migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(settings: Settings, db: sqlite3.Connection) -> Iterator[TestClient]:
    """A TestClient sharing the `db` fixture's file, so tests can inspect state."""
    app = create_app(settings, db_factory=lambda: connect(settings.db_path), migrate=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_client(client: TestClient) -> TestClient:
    """A TestClient with a registered, signed-in user."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "display_name": "Aaro",
            "site_password": TEST_SITE_PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    return client
