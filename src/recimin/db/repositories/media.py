"""Stored media files.

Content-addressed on disk; this table holds only metadata. Rows cascade with
their recipe; the bytes are deleted by the recipe route unless another live
row shares the same sha256.
"""

import sqlite3

from recimin.db.clock import now
from recimin.db.models import Media, MediaKind


def create(
    conn: sqlite3.Connection,
    *,
    kind: MediaKind,
    file_path: str,
    sha256: str,
    bytes_: int,
    mime: str,
    recipe_id: int | None = None,
    position: int = 0,
    source_url: str | None = None,
) -> int:
    """Record a stored file. Returns the new media id."""
    cursor = conn.execute(
        "INSERT INTO media (recipe_id, kind, position, file_path, sha256, bytes, mime,"
        " source_url, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (recipe_id, str(kind), position, file_path, sha256, bytes_, mime, source_url, now()),
    )
    return int(cursor.lastrowid or 0)


def get(conn: sqlite3.Connection, media_id: int) -> Media | None:
    """Fetch one media row, or None."""
    row = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    return Media.from_row(row) if row else None


def find_by_sha256(conn: sqlite3.Connection, sha256: str) -> Media | None:
    """Look up an already-stored file so identical bytes are never written twice."""
    row = conn.execute(
        "SELECT * FROM media WHERE sha256 = ? AND discarded_at IS NULL LIMIT 1", (sha256,)
    ).fetchone()
    return Media.from_row(row) if row else None


def for_recipe(
    conn: sqlite3.Connection, recipe_id: int, *, kind: MediaKind | None = None
) -> list[Media]:
    """A recipe's media, excluding discarded rows, in display order."""
    sql = "SELECT * FROM media WHERE recipe_id = ? AND discarded_at IS NULL"
    params: list[object] = [recipe_id]
    if kind is not None:
        sql += " AND kind = ?"
        params.append(str(kind))
    rows = conn.execute(sql + " ORDER BY position, id", params).fetchall()
    return [Media.from_row(row) for row in rows]


def attach_to_recipe(conn: sqlite3.Connection, media_id: int, recipe_id: int) -> None:
    """Bind an orphan media row to a recipe."""
    conn.execute("UPDATE media SET recipe_id = ? WHERE id = ?", (recipe_id, media_id))


def total_bytes(conn: sqlite3.Connection) -> int:
    """Sum of retained media, for the storage guard."""
    row = conn.execute(
        "SELECT coalesce(sum(bytes), 0) AS n FROM media WHERE discarded_at IS NULL"
    ).fetchone()
    return int(row["n"])
