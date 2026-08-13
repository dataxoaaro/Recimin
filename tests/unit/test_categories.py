"""The fixed category enum.

Keys are permanent: they are stored in the database, so a rename is a data
migration. These tests exist to make an accidental rename fail loudly.
"""

from recimin.db.categories import (
    CATEGORY_META,
    DEFAULT_CATEGORY,
    Category,
    parse_category,
)

EXPECTED_KEYS = {
    "main_course",
    "soup",
    "salad",
    "side_dish",
    "appetizer",
    "breakfast",
    "bread",
    "savoury_baking",
    "sweet_baking",
    "cake",
    "dessert",
    "drink",
    "sauce",
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


def test_parse_accepts_known_keys() -> None:
    assert parse_category("cake") is Category.CAKE
    assert parse_category("  SWEET_BAKING  ") is Category.SWEET_BAKING


def test_parse_degrades_rather_than_raising() -> None:
    """Extraction output is untrusted; an unknown value must not fail an import."""
    assert parse_category("pudding") is DEFAULT_CATEGORY
    assert parse_category(None) is DEFAULT_CATEGORY
    assert parse_category("") is DEFAULT_CATEGORY


def test_default_matches_the_schema_default() -> None:
    """The DB column default and this constant must not drift apart."""
    migration = (
        __import__("pathlib").Path("migrations/0001_initial.sql").read_text(encoding="utf-8")
    )
    assert f"category           TEXT NOT NULL DEFAULT '{DEFAULT_CATEGORY.value}'" in migration
