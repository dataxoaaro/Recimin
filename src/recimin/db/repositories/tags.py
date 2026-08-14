"""Free-form tags.

Names are normalised to lowercase on the way in. Without that the vocabulary
degrades into "Chicken", "chicken" and "CHICKEN" within a month.
"""

import sqlite3


def normalise(name: str) -> str:
    """Collapse whitespace and lowercase. Empty input yields an empty string."""
    return " ".join(name.strip().lower().split())


def get_or_create(conn: sqlite3.Connection, name: str) -> int:
    """Return the id for a tag name, inserting it if new."""
    clean = normalise(name)
    if not clean:
        raise ValueError("tag name cannot be empty")
    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (clean,))
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (clean,)).fetchone()
    return int(row["id"])


def set_for_recipe(conn: sqlite3.Connection, recipe_id: int, names: list[str]) -> None:
    """Replace a recipe's tags with exactly this set."""
    conn.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))
    seen: set[str] = set()
    for name in names:
        clean = normalise(name)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        tag_id = get_or_create(conn, clean)
        conn.execute(
            "INSERT OR IGNORE INTO recipe_tags (recipe_id, tag_id) VALUES (?, ?)",
            (recipe_id, tag_id),
        )


def for_recipe(conn: sqlite3.Connection, recipe_id: int) -> list[str]:
    """A recipe's tag names, alphabetically."""
    rows = conn.execute(
        "SELECT t.name FROM tags t JOIN recipe_tags rt ON rt.tag_id = t.id"
        " WHERE rt.recipe_id = ? ORDER BY t.name",
        (recipe_id,),
    ).fetchall()
    return [row["name"] for row in rows]
