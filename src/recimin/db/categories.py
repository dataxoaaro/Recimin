"""The fixed recipe category enum.

Stored in the database as the English key. Display labels resolve at render time,
so renaming a label never requires a data migration. Adding a category is cheap;
renaming or removing a *key* is not. Treat the keys as permanent.

The dot colour is used only as a small indicator beside the label, never as a
background or as text. See claudedocs/recimin-design.md section 2.
"""

from enum import StrEnum
from typing import NamedTuple


class Category(StrEnum):
    """Recipe categories. One per recipe, required."""

    MAIN_COURSE = "main_course"
    SOUP = "soup"
    SALAD = "salad"
    SIDE_DISH = "side_dish"
    APPETIZER = "appetizer"
    BREAKFAST = "breakfast"
    BREAD = "bread"
    SAVOURY_BAKING = "savoury_baking"
    SWEET_BAKING = "sweet_baking"
    CAKE = "cake"
    DESSERT = "dessert"
    DRINK = "drink"
    SAUCE = "sauce"


class CategoryMeta(NamedTuple):
    """Presentation metadata for a category."""

    label: str
    colour: str


CATEGORY_META: dict[Category, CategoryMeta] = {
    Category.MAIN_COURSE: CategoryMeta("Main course", "#a8502f"),
    Category.SOUP: CategoryMeta("Soup", "#c0752f"),
    Category.SALAD: CategoryMeta("Salad", "#5c8f3a"),
    Category.SIDE_DISH: CategoryMeta("Side dish", "#7a9a4e"),
    Category.APPETIZER: CategoryMeta("Appetizer", "#b8843a"),
    Category.BREAKFAST: CategoryMeta("Breakfast", "#d0a83f"),
    Category.BREAD: CategoryMeta("Bread", "#a07845"),
    Category.SAVOURY_BAKING: CategoryMeta("Savoury baking", "#96613a"),
    Category.SWEET_BAKING: CategoryMeta("Sweet baking", "#b8586e"),
    Category.CAKE: CategoryMeta("Cake", "#c4557f"),
    Category.DESSERT: CategoryMeta("Dessert", "#8a5fa8"),
    Category.DRINK: CategoryMeta("Drink", "#3a8f96"),
    Category.SAUCE: CategoryMeta("Sauce", "#6a6f7a"),
}

DEFAULT_CATEGORY = Category.MAIN_COURSE


def parse_category(value: str | None) -> Category:
    """Coerce an arbitrary string to a Category, falling back to the default.

    Extraction output is untrusted, so an unknown value must degrade rather than
    fail the import.
    """
    if not value:
        return DEFAULT_CATEGORY
    try:
        return Category(value.strip().lower())
    except ValueError:
        return DEFAULT_CATEGORY
