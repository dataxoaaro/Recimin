"""schema.org Recipe normalisation.

The highest-leverage code in the project. Every defect handled here was observed
on a live Finnish recipe page — see claudedocs/recimin-technical.md section 6.7.
Do not simplify a branch away without a fixture proving it is dead.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# "PT", "PTM", "PT0M" and "" all appear in the wild and all mean "no value".
_ISO_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
_LEADING_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_SEO_SUFFIX = re.compile(r"\s*[\u2013\u2014|]\s*.{0,80}$")
_LEADING_INT = re.compile(r"(\d+)")
_WHITESPACE = re.compile(r"\s+")


@dataclass(slots=True)
class NormalisedRecipe:
    """A recipe extracted from structured data, ready to persist.

    `category` is the raw string the source supplied; persist() coerces it to
    the fixed vocabulary with parse_category, so anything is safe to put here.
    """

    title: str
    ingredients: list[str] = field(default_factory=list)
    instructions_md: str = ""
    servings: int | None = None
    yield_text: str | None = None
    total_time_minutes: int | None = None
    description: str | None = None
    image_url: str | None = None
    author: str | None = None
    language: str = "en"
    category: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """A recipe needs a title and at least one of ingredients or method."""
        return bool(self.title) and bool(self.ingredients or self.instructions_md)


def clean_text(value: Any) -> str:
    """Collapse whitespace and normalise unicode.

    NBSP is endemic in scraped recipe text and breaks every downstream split.
    kinuskikissa also emits double spaces inside ingredient lines.
    """
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).replace("\xa0", " ")
    return _WHITESPACE.sub(" ", text).strip()


def parse_duration(value: Any) -> int | None:
    """ISO 8601 duration to whole minutes.

    Returns None for the malformed forms seen live: "PT" (yhteishyva), "PTM"
    (myllynparas), "PT0M" (kinuskikissa, arla) and "".
    """
    text = clean_text(value)
    if not text:
        return None
    match = _ISO_DURATION.match(text)
    if match is None:
        return None
    parts = {k: float(v) for k, v in match.groupdict(default="0").items()}
    minutes = int(parts["days"] * 1440 + parts["hours"] * 60 + parts["minutes"])
    return minutes or None


def parse_yield(value: Any) -> tuple[int | None, str | None]:
    """recipeYield to (servings, free text).

    Handles every shape observed:
      "2, 2 annosta"    -> (2, "2 annosta")   valio
      "4-6 annosta"     -> (4, "4-6 annosta") k-ruoka, en-dash
      "15"              -> (15, None)         kinuskikissa, bare integer
      "10 palaa"        -> (10, "10 palaa")   slices, not servings
      ["4 annosta"]     -> (4, "4 annosta")   list form
    """
    if isinstance(value, list):
        value = value[0] if value else None
    text = clean_text(value)
    if not text:
        return None, None

    # "2, 2 annosta" is a bare count followed by the human form. Prefer the
    # latter, since it carries the unit word.
    if "," in text:
        head, _, tail = text.partition(",")
        if head.strip().isdigit() and tail.strip():
            text = tail.strip()

    match = _LEADING_INT.search(text)
    servings = int(match.group(1)) if match else None

    # A bare integer carries no unit, so there is nothing worth displaying.
    yield_text = None if text.isdigit() else text
    return servings, yield_text


def clean_title(value: Any) -> str:
    """Strip the SEO suffix sites append to <title>-derived names.

    meillakotona ships "Mustikkapiirakka – katso ohje! | Maku".
    """
    text = clean_text(value)
    if not text:
        return ""
    # Strip from the FIRST separator: "Mustikkapiirakka - katso ohje! | Maku"
    # has two, and cutting at the last one keeps the marketing.
    stripped = _SEO_SUFFIX.sub("", text).strip()
    # Only accept the strip if something substantial survives.
    return stripped if len(stripped) >= 3 else text


def node_types(node: dict[str, Any]) -> list[str]:
    """A node's @type coerced to a list — it ships both ways in the wild.

    Microdata via extruct occasionally lands on a bare "type" key, hence the
    fallback.
    """
    value = node.get("@type") or node.get("type") or ""
    return value if isinstance(value, list) else [value]


def flatten_instructions(value: Any) -> list[str]:
    """recipeInstructions, in any of its shapes, to a list of steps.

    The critical case is myllynparas, which splits a single sentence across two
    array entries ("...ja vatkaa" / "kunnes saat..."). Splitting each entry on
    newlines before joining would produce nonsense, so the array is joined
    first and only then re-split.
    """
    if value is None:
        return []

    if isinstance(value, str):
        return _split_lines(value)

    if isinstance(value, dict):
        if "HowToSection" in node_types(value):
            # arla nests steps inside sections.
            return flatten_instructions(value.get("itemListElement"))
        return _split_lines(value.get("text") or value.get("name") or "")

    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if "HowToSection" in node_types(item):
                    parts.extend(flatten_instructions(item))
                    continue
                parts.append(clean_text(item.get("text") or item.get("name") or ""))
            else:
                parts.append(clean_text(item))
        return _merge_fragments(part for part in parts if part)

    return []


def _merge_fragments(parts: Any) -> list[str]:
    """Join array entries that are fragments, keep entries that are steps.

    myllynparas splits one sentence across two entries ("...ja vatkaa" /
    "kunnes saat..."), so a naive one-entry-per-step reading produces nonsense.
    But most sites really do put one step per entry, and joining those would be
    just as wrong.

    The signal is terminal punctuation: an entry that does not end a sentence
    is a fragment and belongs with the next one.
    """
    steps: list[str] = []
    buffer = ""
    for part in parts:
        cleaned = _LEADING_BULLET.sub("", clean_text(part)).strip()
        if not cleaned:
            continue
        buffer = f"{buffer} {cleaned}".strip() if buffer else cleaned
        if buffer.endswith((".", "!", "?", ":")):
            steps.append(buffer)
            buffer = ""
    if buffer:
        steps.append(buffer)
    return steps


def _split_lines(text: str) -> list[str]:
    """Split prose into steps and strip any leading bullet or number."""
    cleaned = clean_text(text)
    if not cleaned:
        return []
    # Split on sentence-ending punctuation followed by a capital, which is how
    # single-blob instructions (meillakotona) present themselves.
    raw = [cleaned] if len(cleaned) < 200 else re.split(r"(?<=[.!?])\s+(?=[A-ZÅÄÖ])", cleaned)
    return [stripped for line in raw if (stripped := _LEADING_BULLET.sub("", line).strip())]


def extract_ingredients(value: Any) -> list[str]:
    """recipeIngredient to clean lines, preserving order and wording."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [cleaned for item in value if (cleaned := clean_text(item))]


def first_text(value: Any) -> str | None:
    """The first non-empty string in a value that may be a string or a list.

    recipeCategory ships both ways: "Dessert" on most sites, ["Jälkiruoat"]
    on WordPress recipe plugins.
    """
    if isinstance(value, list):
        value = value[0] if value else None
    return clean_text(value) or None


def first_image(value: Any) -> str | None:
    """image in any of its shapes: string, list, ImageObject, list thereof."""
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        return first_image(value.get("url") or value.get("contentUrl"))
    if isinstance(value, list):
        for item in value:
            if (found := first_image(item)) is not None:
                return found
    return None


def author_name(value: Any) -> str | None:
    """author, which is a Person dict, a string, or a list of either."""
    if isinstance(value, str):
        return clean_text(value) or None
    if isinstance(value, dict):
        return clean_text(value.get("name")) or None
    if isinstance(value, list):
        for item in value:
            if (found := author_name(item)) is not None:
                return found
    return None


def from_schema_org(node: dict[str, Any]) -> NormalisedRecipe:
    """Turn a schema.org Recipe node into something persistable."""
    servings, yield_text = parse_yield(node.get("recipeYield"))
    steps = flatten_instructions(node.get("recipeInstructions"))

    total = parse_duration(node.get("totalTime"))
    if total is None:
        prep = parse_duration(node.get("prepTime")) or 0
        cook = parse_duration(node.get("cookTime")) or 0
        total = (prep + cook) or None

    return NormalisedRecipe(
        title=clean_title(node.get("name")),
        ingredients=extract_ingredients(node.get("recipeIngredient") or node.get("ingredients")),
        instructions_md="\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)),
        servings=servings,
        yield_text=yield_text,
        total_time_minutes=total,
        description=clean_text(node.get("description")) or None,
        image_url=first_image(node.get("image")),
        author=author_name(node.get("author")),
        language=detect_language(node),
        category=first_text(node.get("recipeCategory")),
    )


def detect_language(node: dict[str, Any]) -> str:
    """Finnish or English, from an explicit tag or a cheap word check."""
    declared = clean_text(node.get("inLanguage")).lower()
    if declared.startswith("fi"):
        return "fi"
    if declared.startswith("en"):
        return "en"

    sample = " ".join(extract_ingredients(node.get("recipeIngredient"))[:8])
    return "fi" if looks_finnish(sample) else "en"


# Finnish units, the umlauts, and the omnipresent "ja". The one heuristic for
# every path — schema.org samples and social captions used to keep separate,
# quietly diverging marker lists for the same question.
_FINNISH_MARKERS = (" dl ", " rkl ", " tl ", " kpl ", "ä", "ö", " ja ")


def looks_finnish(text: str) -> bool:
    """Whether a snippet of recipe text reads as Finnish."""
    lowered = text.lower()
    return any(marker in lowered for marker in _FINNISH_MARKERS)
