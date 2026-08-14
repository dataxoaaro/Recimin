"""The fixed category enum.

Keys are permanent: they are stored in the database, so a rename is a data
migration. These tests exist to make an accidental rename fail loudly.
"""

from pathlib import Path

from recimin.db.categories import (
    CATEGORY_META,
    DEFAULT_CATEGORY,
    LEGACY_ALIASES,
    Category,
    parse_category,
)

EXPECTED_KEYS = {
    "dinner",
    "salad",
    "breakfast",
    "savoury_baking",
    "sweet_baking",
    "cake",
}

# The thirteen-key set this replaced. Every one of them must still resolve.
RETIRED_KEYS = {
    "main_course",
    "soup",
    "side_dish",
    "appetizer",
    "sauce",
    "drink",
    "bread",
    "dessert",
}


def test_keys_are_frozen() -> None:
    """Renaming a key without a migration would orphan every existing recipe."""
    assert {c.value for c in Category} == EXPECTED_KEYS


def test_every_category_has_presentation_metadata() -> None:
    assert set(CATEGORY_META) == set(Category)
    for meta in CATEGORY_META.values():
        assert meta.label
        assert meta.colour.startswith("#")
        assert len(meta.colour) == 7


def test_category_colours_are_distinct() -> None:
    """The dot is the only category signal on a recipe card, so a duplicate
    colour makes two categories indistinguishable there."""
    colours = [meta.colour for meta in CATEGORY_META.values()]
    assert len(set(colours)) == len(colours)


def test_parse_accepts_known_keys() -> None:
    assert parse_category("cake") is Category.CAKE
    assert parse_category("  SWEET_BAKING  ") is Category.SWEET_BAKING


def test_parse_degrades_rather_than_raising() -> None:
    """Extraction output is untrusted; an unknown value must not fail an import."""
    assert parse_category("pudding") is DEFAULT_CATEGORY
    assert parse_category(None) is DEFAULT_CATEGORY
    assert parse_category("") is DEFAULT_CATEGORY


def test_every_retired_key_still_resolves() -> None:
    """A key can arrive from outside the migration — a phone on a cached build,
    a job queued before the deploy, the table's own column default. Falling back
    would turn every one of those into a dinner."""
    assert set(LEGACY_ALIASES) == RETIRED_KEYS
    for key in RETIRED_KEYS:
        assert parse_category(key) in set(Category)


def test_retired_keys_land_where_intended() -> None:
    assert parse_category("bread") is Category.SAVOURY_BAKING
    assert parse_category("dessert") is Category.SWEET_BAKING
    assert parse_category("soup") is Category.DINNER
    assert parse_category("main_course") is Category.DINNER


def test_the_stale_column_default_is_unreachable_but_survivable() -> None:
    """0001 still declares DEFAULT 'main_course'. Altering it means rebuilding a
    table carrying eight FTS triggers, for a default no insert path uses — every
    caller supplies a category. It must at least resolve if it ever fires."""
    initial = Path("migrations/0001_initial.sql").read_text(encoding="utf-8")
    assert "DEFAULT 'main_course'" in initial, "if this changed, drop this test"
    assert parse_category("main_course") is DEFAULT_CATEGORY


def test_the_reduction_migration_covers_every_retired_key() -> None:
    """A key left out of the CASE would keep its old value in the database and
    then vanish from the filter, because the UI only lists current categories."""
    sql = Path("migrations/0002_simplify_categories.sql").read_text(encoding="utf-8")
    for key in RETIRED_KEYS:
        assert f"'{key}'" in sql, f"{key} is not remapped by the migration"
