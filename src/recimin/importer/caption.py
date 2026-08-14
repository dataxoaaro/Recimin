"""The caption gate.

Before downloading anything, ask whether the caption already *is* the recipe.
When it is, the import costs one metadata request and nothing else.

There is no published data on how often that happens. The widely-quoted "80% of
creators put ingredients in the caption" figure does not appear in either of the
sources it is attributed to. So the gate records its own verdict on every job,
and after a hundred imports the answer is measured rather than assumed.
"""

import re

from recimin.importer.ingredients import UNITS

# A quantity at the start of a line: "2 dl", "1½ rkl", "200 g", "1 kpl",
# "2 cups", "½ tsp". The vocabulary is the parser's own — one list to keep
# updated, not two — plus caption-only words the parser never sees in
# structured lines. Longest-first so "kg" cannot lose to "g" in alternation.
_CAPTION_ONLY = ("pinch", "clove", "cloves", "ounce", "ounces", "tbsps", "tsps")
_UNITS = "|".join(
    sorted({re.escape(unit) for unit in (*UNITS, *_CAPTION_ONLY)}, key=len, reverse=True)
)
_QUANTITY_LINE = re.compile(
    rf"^\s*(?:\d+[.,]?\d*|[½¼¾⅓⅔⅛]|\d+\s*[½¼¾⅓⅔⅛])\s*(?:{_UNITS})?\b",
    re.IGNORECASE,
)
_HASHTAG_LINE = re.compile(r"^\s*(?:#\w+\s*)+$")

MIN_QUANTITY_LINES = 3


def content_lines(caption: str) -> list[str]:
    """Caption lines with hashtag-only lines and blanks removed."""
    return [
        stripped
        for line in caption.splitlines()
        if (stripped := line.strip()) and not _HASHTAG_LINE.match(stripped)
    ]


def count_quantity_lines(caption: str) -> int:
    """How many lines look like an ingredient with an amount."""
    return sum(1 for line in content_lines(caption) if _QUANTITY_LINE.match(line))


def looks_like_a_recipe(caption: str) -> bool:
    """Whether the caption alone carries enough to skip extraction."""
    return count_quantity_lines(caption) >= MIN_QUANTITY_LINES


def strip_hashtags(caption: str) -> str:
    """Caption without its trailing hashtag block, for use as a title source."""
    return "\n".join(content_lines(caption)).strip()


MAX_TITLE = 80


def title_from_caption(caption: str, fallback: str) -> str:
    """A usable title from a caption's first meaningful line.

    Captions rarely open with a title. The Kinder cheesecake post opens with a
    122-character sentence of prose, so a plain length limit would discard it
    and fall back to "instagram post DWjfQTDNm_l" — strictly worse than a
    trimmed sentence. Take the first sentence, then trim on a word boundary.
    """
    for line in content_lines(caption):
        # Skip lines that are themselves ingredients.
        if _QUANTITY_LINE.match(line):
            continue
        cleaned = re.sub(r"#\w+", "", line).strip(" -\u2013\u2014:\u2022.")
        if len(cleaned) < 3:
            continue
        sentence = re.split(r"(?<=[.!?])\s", cleaned, maxsplit=1)[0].strip(" .")
        if len(sentence) <= MAX_TITLE:
            return sentence
        head = sentence[:MAX_TITLE].rsplit(" ", 1)[0]
        return f"{head}\u2026"
    return fallback
