"""Ingredient lines.

Ingredients are always replaced wholesale rather than patched individually. An
edit form submits the whole list, and reordering by patching positions against a
UNIQUE(recipe_id, position) constraint is a source of avoidable conflicts.
"""

import sqlite3
from dataclasses import dataclass

from recimin.db.models import Ingredient


@dataclass(frozen=True, slots=True)
class IngredientDraft:
    """One line to store.

    Only raw_text is required. Everything else is opportunistic parser output and
    None is the normal case, not a failure.
    """

    raw_text: str
    original_text: str | None = None
    qty: float | None = None
    unit: str | None = None
    item: str | None = None
    note: str | None = None
    group_label: str | None = None
    alternative_of: int | None = None


def replace_all(conn: sqlite3.Connection, recipe_id: int, lines: list[IngredientDraft]) -> None:
    """Replace every ingredient for a recipe, renumbering positions from zero."""
    conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
    conn.executemany(
        "INSERT INTO ingredients"
        " (recipe_id, position, raw_text, original_text, qty, unit, item, note,"
        "  group_label, alternative_of)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                recipe_id,
                position,
                line.raw_text,
                line.original_text,
                line.qty,
                line.unit,
                line.item,
                line.note,
                line.group_label,
                line.alternative_of,
            )
            for position, line in enumerate(lines)
        ],
    )


def for_recipe(conn: sqlite3.Connection, recipe_id: int) -> list[Ingredient]:
    """Every ingredient for a recipe, in display order."""
    rows = conn.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY position", (recipe_id,)
    ).fetchall()
    return [Ingredient.from_row(row) for row in rows]
