"""Application configuration, loaded from the environment and validated at startup.

Required secrets have no defaults. A missing one raises at import time rather than
producing a subtly insecure runtime, which is the failure mode that matters here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Runtime configuration. See .env.example for the full set."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets. No defaults on purpose.
    jwt_secret: str = Field(min_length=32)
    site_password: str = Field(min_length=8)

    # Storage
    data_dir: Path = Path("/data")
    max_media_bytes: int = 80_000_000_000

    # HTTP
    allowed_origin: str = "http://localhost:5173"
    scraper_user_agent: str = DEFAULT_USER_AGENT

    # LLM
    llm_enabled: bool = True
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-3.7-flash"
    openrouter_model_fallback: str = "google/gemini-3.5-flash-lite"
    # Gemini's thinking level. "medium" is Google's own default and the right
    # one here: extraction is a first-pass accuracy task, not hard reasoning.
    # "low" trades accuracy for latency; "high" spends tokens on extended
    # thought this job does not need. Sent explicitly rather than relied on, so
    # a change to the provider default cannot silently alter our cost.
    openrouter_reasoning_effort: str = "medium"

    @field_validator("data_dir")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "recimin.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
