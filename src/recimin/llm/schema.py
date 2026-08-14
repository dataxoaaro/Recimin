"""The extraction contract.

A strict JSON schema sent to OpenRouter, mirrored as Pydantic models so the
response is validated on our side too. Structured-output support is decided per
*endpoint*, not per model — the same model from two providers may honour the
schema on one and treat it as a hint on the other — so client-side validation
is not belt and braces, it is the actual guarantee.
"""

from typing import Any

from pydantic import BaseModel, Field

from recimin.db.categories import Category

CATEGORY_KEYS = [str(c) for c in Category]

# A controlled vocabulary. Free-form tags degrade into "quick", "Quick" and
# "fast" within a month.
SUGGESTED_TAGS = [
    "quick",
    "weeknight",
    "party",
    "freezer",
    "vegetarian",
    "vegan",
    "gluten-free",
    "dairy-free",
    "one-pot",
    "make-ahead",
    "budget",
    "kids",
    "summer",
    "winter",
    "christmas",
    "grill",
]

SUGGESTED_TAG_SET = frozenset(SUGGESTED_TAGS)


class ExtractedIngredient(BaseModel):
    """One ingredient line.

    raw_text is what gets displayed. original_text is only set when units were
    converted, so the review screen can show what the author actually wrote.
    """

    raw_text: str = Field(max_length=500)
    original_text: str | None = Field(default=None, max_length=500)
    qty: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    item: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=200)
    group_label: str | None = Field(default=None, max_length=80)
    alternative_of: int | None = None


class ExtractedRecipe(BaseModel):
    """A recipe as the model returns it."""

    title: str = Field(max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    language: str = Field(pattern="^(fi|en)$")
    category: str
    servings: int | None = Field(default=None, ge=1, le=999)
    yield_text: str | None = Field(default=None, max_length=80)
    total_time_minutes: int | None = Field(default=None, ge=0, le=100_000)
    tags: list[str] = Field(default_factory=list, max_length=6)
    ingredients: list[ExtractedIngredient] = Field(default_factory=list, max_length=200)
    instructions_md: str = Field(default="", max_length=50_000)
    confidence: str = Field(default="medium", pattern="^(high|medium|low)$")


def json_schema() -> dict[str, Any]:
    """The schema sent to the provider.

    Hand-written rather than generated from the Pydantic model: OpenAI rejects
    `pattern` in structured outputs, and providers vary in which keywords they
    accept. This stays deliberately plain.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "language", "category", "ingredients", "instructions_md"],
        "properties": {
            "title": {"type": "string"},
            "description": {"type": ["string", "null"]},
            "language": {"enum": ["fi", "en"]},
            "category": {"enum": CATEGORY_KEYS},
            "servings": {"type": ["integer", "null"]},
            "yield_text": {"type": ["string", "null"]},
            "total_time_minutes": {"type": ["integer", "null"]},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["raw_text"],
                    "properties": {
                        "raw_text": {"type": "string"},
                        "original_text": {"type": ["string", "null"]},
                        "qty": {"type": ["number", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "item": {"type": ["string", "null"]},
                        "note": {"type": ["string", "null"]},
                        "group_label": {"type": ["string", "null"]},
                        "alternative_of": {"type": ["integer", "null"]},
                    },
                },
            },
            "instructions_md": {"type": "string"},
            "confidence": {"enum": ["high", "medium", "low"]},
        },
    }
