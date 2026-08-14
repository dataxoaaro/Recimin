"""Row types.

Frozen dataclasses, one per table. Repositories return these; nothing outside
the db package handles a sqlite3.Row.
"""

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class RecipeStatus(StrEnum):
    """A recipe is a draft until a human has confirmed the extraction."""

    DRAFT = "draft"
    PUBLISHED = "published"


class SourcePlatform(StrEnum):
    """Where a recipe came from."""

    WEB = "web"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    MANUAL = "manual"


class MediaKind(StrEnum):
    """What a stored file is."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class JobStatus(StrEnum):
    """Import job lifecycle.

    NEEDS_ATTENTION is distinct from FAILED: it means a human must look, usually
    because an extractor broke rather than because the input was bad.
    """

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"


class JobStage(StrEnum):
    """Progress within a running import, surfaced in the Imports screen."""

    RESOLVE = "resolve"
    FETCH = "fetch"
    MEDIA = "media"
    EXTRACT = "extract"
    PERSIST = "persist"


class CaptionGate(StrEnum):
    """Whether the caption alone already contained the recipe."""

    HIT = "hit"
    MISS = "miss"


@dataclass(frozen=True, slots=True)
class User:
    id: int
    email: str
    password_hash: str
    display_name: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            email=row["email"],
            password_hash=row["password_hash"],
            display_name=row["display_name"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class ApiToken:
    id: int
    user_id: int
    name: str
    token_hash: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            token_hash=row["token_hash"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
        )


@dataclass(frozen=True, slots=True)
class Ingredient:
    """One ingredient line.

    raw_text is the source of truth and is always what gets displayed. The
    parsed fields are opportunistic; None is normal and never an error.
    """

    id: int
    recipe_id: int
    position: int
    raw_text: str
    original_text: str | None = None
    qty: float | None = None
    unit: str | None = None
    item: str | None = None
    note: str | None = None
    group_label: str | None = None
    alternative_of: int | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            recipe_id=row["recipe_id"],
            position=row["position"],
            raw_text=row["raw_text"],
            original_text=row["original_text"],
            qty=row["qty"],
            unit=row["unit"],
            item=row["item"],
            note=row["note"],
            group_label=row["group_label"],
            alternative_of=row["alternative_of"],
        )


@dataclass(frozen=True, slots=True)
class Media:
    id: int
    recipe_id: int | None
    kind: MediaKind
    position: int
    file_path: str
    sha256: str
    bytes: int
    mime: str
    created_at: str
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    source_url: str | None = None
    discarded_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            recipe_id=row["recipe_id"],
            kind=MediaKind(row["kind"]),
            position=row["position"],
            file_path=row["file_path"],
            sha256=row["sha256"],
            bytes=row["bytes"],
            mime=row["mime"],
            created_at=row["created_at"],
            width=row["width"],
            height=row["height"],
            duration_s=row["duration_s"],
            source_url=row["source_url"],
            discarded_at=row["discarded_at"],
        )


@dataclass(frozen=True, slots=True)
class Recipe:
    id: int
    title: str
    instructions_md: str
    category: str
    language: str
    is_favourite: bool
    status: RecipeStatus
    created_at: str
    updated_at: str
    description: str | None = None
    notes: str | None = None
    servings: int | None = None
    yield_text: str | None = None
    total_time_minutes: int | None = None
    hero_media_id: int | None = None
    source_url: str | None = None
    source_url_normalised: str | None = None
    source_site: str | None = None
    source_author: str | None = None
    source_title: str | None = None
    source_platform: SourcePlatform | None = None
    imported_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        platform = row["source_platform"]
        return cls(
            id=row["id"],
            title=row["title"],
            instructions_md=row["instructions_md"],
            category=row["category"],
            language=row["language"],
            is_favourite=bool(row["is_favourite"]),
            status=RecipeStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            description=row["description"],
            notes=row["notes"],
            servings=row["servings"],
            yield_text=row["yield_text"],
            total_time_minutes=row["total_time_minutes"],
            hero_media_id=row["hero_media_id"],
            source_url=row["source_url"],
            source_url_normalised=row["source_url_normalised"],
            source_site=row["source_site"],
            source_author=row["source_author"],
            source_title=row["source_title"],
            source_platform=SourcePlatform(platform) if platform else None,
            imported_at=row["imported_at"],
        )


@dataclass(frozen=True, slots=True)
class RecipeListing:
    """The card-sized slice of a recipe, for the library grid.

    A separate type so the listing query can skip instructions_md — the recipe
    body, kilobytes per row for imports that embed a transcript — instead of
    reading it 500 rows at a time and throwing it away.
    """

    id: int
    title: str
    category: str
    language: str
    is_favourite: bool
    status: RecipeStatus
    created_at: str
    servings: int | None = None
    total_time_minutes: int | None = None
    hero_media_id: int | None = None
    source_platform: SourcePlatform | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        platform = row["source_platform"]
        return cls(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            language=row["language"],
            is_favourite=bool(row["is_favourite"]),
            status=RecipeStatus(row["status"]),
            created_at=row["created_at"],
            servings=row["servings"],
            total_time_minutes=row["total_time_minutes"],
            hero_media_id=row["hero_media_id"],
            source_platform=SourcePlatform(platform) if platform else None,
        )


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    kind: str
    status: JobStatus
    input_url: str
    attempts: int
    created_at: str
    stage: JobStage | None = None
    normalised_url: str | None = None
    platform: str | None = None
    recipe_id: int | None = None
    last_error: str | None = None
    caption_gate: CaptionGate | None = None
    created_by: int | None = None
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self:
        return cls(
            id=row["id"],
            kind=row["kind"],
            status=JobStatus(row["status"]),
            input_url=row["input_url"],
            attempts=row["attempts"],
            created_at=row["created_at"],
            stage=JobStage(row["stage"]) if row["stage"] else None,
            normalised_url=row["normalised_url"],
            platform=row["platform"],
            recipe_id=row["recipe_id"],
            last_error=row["last_error"],
            caption_gate=CaptionGate(row["caption_gate"]) if row["caption_gate"] else None,
            created_by=row["created_by"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
