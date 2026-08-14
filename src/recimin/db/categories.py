"""The fixed recipe category enum.

Stored in the database as the English key. Display labels resolve at render time,
so renaming a label never requires a data migration.

Six, not thirteen. The original set carved the space finely enough that the
filter row no longer fitted a phone screen, and the distinctions it drew were
ones nobody makes when looking for something to cook: soup, side dish, appetizer
and sauce were all just "dinner", and bread is savoury baking. A filter is only
useful if picking one meaningfully narrows the library, and with thirteen
categories over a household's few hundred recipes most held one or two.

The LLM assigns the category during extraction, so a coarser set is also an
easier judgement for it to get right — there is no longer a meaningful call to
make between "dessert" and "sweet baking".

The dot colour is used only as a small indicator beside the label, never as a
background or as text. See claudedocs/recimin-design.md section 2.
"""

import re
from enum import StrEnum
from typing import NamedTuple


class Category(StrEnum):
    """Recipe categories. One per recipe, required."""

    DINNER = "dinner"
    SALAD = "salad"
    BREAKFAST = "breakfast"
    SAVOURY_BAKING = "savoury_baking"
    SWEET_BAKING = "sweet_baking"
    CAKE = "cake"


class CategoryMeta(NamedTuple):
    """Presentation metadata for a category."""

    label: str
    colour: str


CATEGORY_META: dict[Category, CategoryMeta] = {
    Category.DINNER: CategoryMeta("Dinner", "#a8502f"),
    Category.SALAD: CategoryMeta("Salad", "#5c8f3a"),
    Category.BREAKFAST: CategoryMeta("Breakfast", "#d0a83f"),
    Category.SAVOURY_BAKING: CategoryMeta("Savoury baking", "#96613a"),
    Category.SWEET_BAKING: CategoryMeta("Sweet baking", "#b8586e"),
    Category.CAKE: CategoryMeta("Cake", "#c4557f"),
}

DEFAULT_CATEGORY = Category.DINNER

# Keys from the thirteen-category set, mapped to where they now live.
#
# Kept rather than deleted because a key can still arrive from outside the
# migration: a phone running a cached build, a queued import created before the
# deploy, or the recipes table's own column default, which SQLite cannot alter
# without rebuilding a table that carries FTS triggers. Resolving these to the
# right home beats silently collapsing them all to the fallback.
#
# "drink" is the one genuinely poor fit — nothing in the new set describes a
# smoothie. It maps to dinner because the alternative is losing the row, and no
# drink recipes existed when the set was reduced.
LEGACY_ALIASES: dict[str, Category] = {
    "main_course": Category.DINNER,
    "soup": Category.DINNER,
    "side_dish": Category.DINNER,
    "appetizer": Category.DINNER,
    "sauce": Category.DINNER,
    "drink": Category.DINNER,
    "bread": Category.SAVOURY_BAKING,
    "dessert": Category.SWEET_BAKING,
}


def parse_category(value: str | None) -> Category:
    """Coerce an arbitrary string to a Category, falling back to the default.

    Extraction output is untrusted, so an unknown value must degrade rather than
    fail the import. Retired keys resolve to their successor rather than the
    fallback, so a stale client does not turn every cake into a dinner.
    """
    if not value:
        return DEFAULT_CATEGORY

    # Spaces and hyphens become underscores so schema.org's human-facing
    # strings ("Main course", "Side Dish") land on the same keys.
    key = re.sub(r"[\s\-]+", "_", value.strip().lower())
    try:
        return Category(key)
    except ValueError:
        return LEGACY_ALIASES.get(key, DEFAULT_CATEGORY)
