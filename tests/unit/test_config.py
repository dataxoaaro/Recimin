"""Configuration validation.

The point of these tests is that a missing or weak secret fails loudly at startup
rather than producing a quietly insecure runtime.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from recimin.config import Settings

VALID_SECRET = "x" * 32


def test_requires_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(site_password="site-password")  # type: ignore[call-arg]


def test_requires_site_password() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret=VALID_SECRET)  # type: ignore[call-arg]


def test_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="too-short", site_password="site-password")


def test_rejects_short_site_password() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret=VALID_SECRET, site_password="short")


def test_derived_paths(tmp_path: Path) -> None:
    settings = Settings(jwt_secret=VALID_SECRET, site_password="site-password", data_dir=tmp_path)
    assert settings.db_path == tmp_path / "recimin.db"
    assert settings.media_dir == tmp_path / "media"


def test_user_agent_is_a_current_chrome_string() -> None:
    """A stale UA is the single most likely cause of a silent TikTok failure."""
    settings = Settings(jwt_secret=VALID_SECRET, site_password="site-password")
    assert "Chrome/" in settings.scraper_user_agent
    assert "yt-dlp" not in settings.scraper_user_agent
