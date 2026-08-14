"""Recipe reads and writes.

A recipe, its ingredients and its tags are written together in one transaction:
a half-saved recipe is worse than a failed save.
"""

import sqlite3
from dataclasses import dataclass

from recimin.db.clock import now
from recimin.db.connection import transaction
from recimin.db.models import Recipe, RecipeListing, RecipeStatus, SourcePlatform
from recimin.db.repositories import ingredients as ingredients_repo
from recimin.db.repositories import tags as tags_repo

_COLUMNS = (
    "title",
    "description",
    "instructions_md",
    "notes",
    "servings",
    "yield_text",
    "total_time_minutes",
    "category",
    "language",
    "is_favourite",
    "status",
    "hero_media_id",
    "source_url",
    "source_url_normalised",
    "source_site",
    "source_author",
    "source_title",
    "source_platform",
    "imported_at",
)


@dataclass(frozen=True, slots=True)
class RecipeDraft:
    """Everything needed to create or replace a recipe."""

    title: str
    instructions_md: str = ""
    category: str = "dinner"
    language: str = "en"
    status: RecipeStatus = RecipeStatus.DRAFT
    description: str | None = None
    notes: str | None = None
    servings: int | None = None
    yield_text: str | None = None
    total_time_minutes: int | None = None
    is_favourite: bool = False
    hero_media_id: int | None = None
    source_url: str | None = None
    source_url_normalised: str | None = None
    source_site: str | None = None
    source_author: str | None = None
    source_title: str | None = None
    source_platform: SourcePlatform | None = None
    imported_at: str | None = None

    def as_params(self) -> dict[str, object]:
        """Flatten to the column set, coercing enums and bools for SQLite."""
        return {
            "title": self.title,
            "description": self.description,
            "instructions_md": self.instructions_md,
            "notes": self.notes,
            "servings": self.servings,
            "yield_text": self.yield_text,
            "total_time_minutes": self.total_time_minutes,
            "category": self.category,
            "language": self.language,
            "is_favourite": int(self.is_favourite),
            "status": str(self.status),
            "hero_media_id": self.hero_media_id,
            "source_url": self.source_url,
            "source_url_normalised": self.source_url_normalised,
            "source_site": self.source_site,
            "source_author": self.source_author,
            "source_title": self.source_title,
            "source_platform": str(self.source_platform) if self.source_platform else None,
            "imported_at": self.imported_at,
        }


def create(
    conn: sqlite3.Connection,
    draft: RecipeDraft,
    *,
    ingredient_lines: list[ingredients_repo.IngredientDraft] | None = None,
    tag_names: list[str] | None = None,
) -> int:
    """Insert a recipe with its ingredients and tags. Returns the new id."""
    params = draft.as_params()
    stamp = now()
    params["created_at"] = stamp
    params["updated_at"] = stamp

    names = ", ".join(params)
    holes = ", ".join(f":{k}" for k in params)

    with transaction(conn):
        cursor = conn.execute(f"INSERT INTO recipes ({names}) VALUES ({holes})", params)
        recipe_id = int(cursor.lastrowid or 0)
        if ingredient_lines:
            ingredients_repo.replace_all(conn, recipe_id, ingredient_lines)
        if tag_names:
            tags_repo.set_for_recipe(conn, recipe_id, tag_names)
    return recipe_id


def get(conn: sqlite3.Connection, recipe_id: int) -> Recipe | None:
    """Fetch one recipe, or None."""
    row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return Recipe.from_row(row) if row else None


def get_by_normalised_url(conn: sqlite3.Connection, url: str) -> Recipe | None:
    """Dedupe lookup. The caller resolves redirects and normalises before calling."""
    row = conn.execute("SELECT * FROM recipes WHERE source_url_normalised = ?", (url,)).fetchone()
    return Recipe.from_row(row) if row else None


def update(conn: sqlite3.Connection, recipe_id: int, **fields: object) -> None:
    """Patch named columns. Unknown columns raise rather than being ignored."""
    unknown = set(fields) - set(_COLUMNS)
    if unknown:
        raise ValueError(f"unknown recipe columns: {sorted(unknown)}")
    if not fields:
        return

    if "is_favourite" in fields:
        fields["is_favourite"] = int(bool(fields["is_favourite"]))
    for enum_field in ("status", "source_platform"):
        if fields.get(enum_field) is not None:
            fields[enum_field] = str(fields[enum_field])

    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "id": recipe_id, "updated_at": now()}
    conn.execute(
        f"UPDATE recipes SET {assignments}, updated_at = :updated_at WHERE id = :id", params
    )


def delete(conn: sqlite3.Connection, recipe_id: int) -> bool:
    """Remove a recipe. Children cascade. Returns whether a row was removed."""
    cursor = conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    return cursor.rowcount > 0


def set_favourite(conn: sqlite3.Connection, recipe_id: int, value: bool) -> None:
    """Toggle the favourite flag."""
    update(conn, recipe_id, is_favourite=value)


def list_recipes(
    conn: sqlite3.Connection,
    *,
    query: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    favourite: bool | None = None,
    status: RecipeStatus | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[RecipeListing]:
    """Filtered listing, newest first.

    A text query joins the FTS index; the remaining filters are plain indexed
    predicates and compose freely with it. Returns card-sized listings rather
    than full rows: the response never carries the recipe bodies, so neither
    should the query.
    """
    where: list[str] = []
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if query:
        where.append("r.id IN (SELECT rowid FROM recipes_fts WHERE recipes_fts MATCH :q)")
        params["q"] = _fts_query(query)
    if category:
        where.append("r.category = :category")
        params["category"] = category
    if favourite is not None:
        where.append("r.is_favourite = :favourite")
        params["favourite"] = int(favourite)
    if status is not None:
        where.append("r.status = :status")
        params["status"] = str(status)
    if tag:
        where.append(
            "r.id IN (SELECT rt.recipe_id FROM recipe_tags rt"
            " JOIN tags t ON t.id = rt.tag_id WHERE t.name = :tag)"
        )
        params["tag"] = tag

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    columns = (
        "r.id, r.title, r.category, r.language, r.is_favourite, r.status, r.created_at,"
        " r.servings, r.total_time_minutes, r.hero_media_id, r.source_platform"
    )
    rows = conn.execute(
        f"SELECT {columns} FROM recipes r {clause}"
        " ORDER BY r.created_at DESC, r.id DESC LIMIT :limit OFFSET :offset",
        params,
    ).fetchall()
    return [RecipeListing.from_row(row) for row in rows]


def _fts_query(raw: str) -> str:
    """Turn free text into a safe FTS5 prefix query.

    FTS5 MATCH has its own syntax, and an unescaped apostrophe or operator from a
    search box is a syntax error rather than zero results. Every token is quoted
    and given a prefix wildcard so typing part of a word still matches.
    """
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in raw).split() if t]
    if not tokens:
        return '""'
    return " ".join(f'"{token}"*' for token in tokens)
