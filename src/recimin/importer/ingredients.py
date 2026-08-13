"""Ingredient line parsing.

Deterministic, and hand-rolled rather than library-based. Finnish is rigidly
`[quantity] [unit] [name-in-partitive]` with a small closed unit set and no
cups anywhere, so a compact grammar beats 39MB of CRF machinery — and it lets
us own the two numeric bugs below, which both available libraries get wrong.

Two bugs that silently corrupt data rather than failing:

  1. Vulgar fractions. Naive replacement turns "1½" into the string "11/2",
     which evaluates to 5.5 rather than 1.5. myllynparas ships "1½ dl" live.
  2. Finnish decimal commas. "2,5 dl" must be 2.5, not 25 and not 10.

`ingreedypy` has both, and additionally fails on `tl` — the single commonest
Finnish unit — because its grammar matches the `t` alias for teaspoon and will
not backtrack.
"""

import re
from dataclasses import dataclass
from fractions import Fraction

VULGAR = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5),
    "⅙": Fraction(1, 6),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
}

# Finnish first: these are what actually appear. tl is 5 ml and rkl is 15 ml,
# which is NOT the same as a US tsp (4.93) or tbsp (14.79) — never alias them.
UNITS = {
    "dl": "dl",
    "l": "l",
    "ml": "ml",
    "cl": "cl",
    "g": "g",
    "kg": "kg",
    "rkl": "rkl",
    "tl": "tl",
    "kpl": "kpl",
    "prk": "prk",
    "ps": "ps",
    "pkt": "pkt",
    "tlk": "tlk",
    "nippu": "nippu",
    "pss": "pss",
    "cup": "cup",
    "cups": "cup",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "oz": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "gram": "g",
    "grams": "g",
    "kilo": "kg",
}

_NOTE = re.compile(r"\s*[(\uff08]([^)\uff09]*)[)\uff09]\s*")
_ALTERNATIVE_SUFFIX = re.compile(r"\s+(TAI|OR)\s*$", re.IGNORECASE)

# A token that is entirely quantity-ish: digits, a vulgar fraction, a slash
# fraction, or a range. Deliberately whole-token: a single regex over the line
# with a non-greedy quantity group matches "2" out of "200".
_QUANTITY_TOKEN = re.compile(
    r"^(?:\d+(?:[.,]\d+)?|[\u00bd\u2153\u2154\u00bc\u00be\u2155\u2159\u215b\u215c\u215d\u215e]"
    r"|\d+/\d+"
    r"|\d+(?:[.,]\d+)?\s*[-\u2013\u2014]\s*\d+(?:[.,]\d+)?)$"
)
# A number with a vulgar fraction glued to it, e.g. "1\u00bd".
_ATTACHED_FRACTION = re.compile(
    r"^\d+[\u00bd\u2153\u2154\u00bc\u00be\u2155\u2159\u215b\u215c\u215d\u215e]$"
)


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """One parsed ingredient. Every field except raw_text may be None."""

    raw_text: str
    qty: float | None = None
    unit: str | None = None
    item: str | None = None
    note: str | None = None
    introduces_alternative: bool = False


def normalise_numeric(text: str) -> str:
    """Make a quantity string safe to evaluate.

    The space before a vulgar fraction is the whole trick: without it "1½"
    becomes "11/2" and parses as 5.5.
    """
    # Separate a leading integer from an attached vulgar fraction.
    spaced = re.sub(r"(?<=\d)(?=[½⅓⅔¼¾⅕⅙⅛⅜⅝⅞])", " ", text)
    # Finnish decimal comma. Only between digits, so "2, 3 dl" is untouched.
    return re.sub(r"(?<=\d),(?=\d)", ".", spaced)


def parse_quantity(text: str) -> float | None:
    """Parse a quantity, handling mixed numbers, fractions and ranges.

    A range ("2-3 dl") takes its lower bound: under-buying is recoverable in a
    way that mis-scaling a recipe is not.
    """
    cleaned = normalise_numeric(text).strip()
    if not cleaned:
        return None

    # A range: take the first operand. En-dash included.
    cleaned = re.split(r"\s*[-–—]\s*", cleaned)[0].strip()
    if not cleaned:
        return None

    total = Fraction(0)
    found = False
    for token in cleaned.split():
        if token in VULGAR:
            total += VULGAR[token]
            found = True
        elif "/" in token:
            try:
                total += Fraction(token)
                found = True
            except (ValueError, ZeroDivisionError):
                return None
        else:
            try:
                total += Fraction(token)
                found = True
            except ValueError:
                return None

    return float(total) if found else None


def parse(raw: str) -> ParsedLine:
    """Parse one ingredient line. Never raises; unparseable is not an error."""
    text = raw.strip()
    if not text:
        return ParsedLine(raw_text=raw)

    alternative = bool(_ALTERNATIVE_SUFFIX.search(text))
    body = _ALTERNATIVE_SUFFIX.sub("", text).strip()

    # Pull out a parenthetical before matching, so "(400 g)" does not read as
    # the line's quantity.
    note = None
    if match := _NOTE.search(body):
        note = match.group(1).strip() or None
        body = _NOTE.sub(" ", body).strip()

    # Ranges are written both "2-3" and "2 - 3"; collapse the spaced form so it
    # survives tokenisation as one quantity.
    body = re.sub(r"(?<=\d)\s*[-\u2013\u2014]\s*(?=\d)", "-", body)
    tokens = body.split()

    # Leading quantity tokens: "1", "1 1/2", "1 \u00bd", "2-3".
    quantity_tokens: list[str] = []
    index = 0
    while index < len(tokens) and (
        _QUANTITY_TOKEN.match(tokens[index]) or _ATTACHED_FRACTION.match(tokens[index])
    ):
        quantity_tokens.append(tokens[index])
        index += 1

    qty = parse_quantity(" ".join(quantity_tokens)) if quantity_tokens else None

    unit = None
    if index < len(tokens):
        candidate = tokens[index].rstrip(".").lower()
        if candidate in UNITS:
            unit = UNITS[candidate]
            index += 1

    item = " ".join(tokens[index:]).strip(" ,.") or None

    return ParsedLine(
        raw_text=raw,
        qty=qty,
        unit=unit,
        item=item,
        note=note,
        introduces_alternative=alternative,
    )


def alternative_positions(lines: list[str]) -> dict[int, int]:
    """Map position -> the position it is an alternative to."""
    links: dict[int, int] = {}
    for index in range(1, len(lines)):
        if _ALTERNATIVE_SUFFIX.search(lines[index - 1].strip()):
            links[index] = index - 1
    return links
