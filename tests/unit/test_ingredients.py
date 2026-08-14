"""Ingredient parsing.

The fraction tests are the important ones. Both bugs produce a plausible wrong
number rather than an error, so nothing else would catch them.
"""

import pytest

from recimin.importer.ingredients import (
    alternative_positions,
    normalise_numeric,
    parse,
    parse_quantity,
)

# ─── the two corrupting bugs ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected", "wrong"),
    [
        ("1½", 1.5, 5.5),
        ("2½", 2.5, 10.5),
        ("3¾", 3.75, 8.25),
        ("1¼", 1.25, 4.25),
    ],
)
def test_attached_vulgar_fractions(raw: str, expected: float, wrong: float) -> None:
    """Naive replacement turns "1½" into "11/2" = 5.5. myllynparas ships this live."""
    result = parse_quantity(raw)
    assert result == expected
    assert result != wrong


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2,5", 2.5), ("0,5", 0.5), ("1,25", 1.25)],
)
def test_finnish_decimal_commas(raw: str, expected: float) -> None:
    """ingreedypy parses "2,5" as 10. It must be 2.5."""
    assert parse_quantity(raw) == expected


def test_a_comma_between_words_is_not_a_decimal_point() -> None:
    assert normalise_numeric("2, 3") == "2, 3"


# ─── quantities ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2", 2.0),
        ("½", 0.5),
        ("1 ½", 1.5),
        ("3/4", 0.75),
        ("1 1/2", 1.5),
        ("2-3", 2.0),  # a range takes its lower bound
        ("2–3", 2.0),  # en-dash
        ("", None),
        ("some", None),
    ],
)
def test_quantity_shapes(raw: str, expected: float | None) -> None:
    assert parse_quantity(raw) == expected


# ─── Finnish lines ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "qty", "unit", "item"),
    [
        ("2 dl kermaa", 2.0, "dl", "kermaa"),
        ("1 tl suolaa", 1.0, "tl", "suolaa"),
        ("1½ dl vehnäjauhoja", 1.5, "dl", "vehnäjauhoja"),
        ("2 rkl voita", 2.0, "rkl", "voita"),
        ("200 g mansikoita", 200.0, "g", "mansikoita"),
        ("1 kg perunoita", 1.0, "kg", "perunoita"),
        ("3 kpl kananmunia", 3.0, "kpl", "kananmunia"),
        ("1 prk tomaattimurskaa", 1.0, "prk", "tomaattimurskaa"),
        ("0,5 l maitoa", 0.5, "l", "maitoa"),
        ("2,5 dl sokeria", 2.5, "dl", "sokeria"),
    ],
)
def test_finnish_grammar(line: str, qty: float, unit: str, item: str) -> None:
    parsed = parse(line)
    assert parsed.qty == qty
    assert parsed.unit == unit
    assert parsed.item == item
    assert parsed.raw_text == line


def test_tl_is_not_aliased_to_tsp() -> None:
    """tl is 5ml; a US tsp is 4.93. Conflating them is a silent 1.4% error."""
    assert parse("1 tl suolaa").unit == "tl"
    assert parse("1 tsp salt").unit == "tsp"


@pytest.mark.parametrize(
    ("line", "qty", "unit"),
    [
        ("2 cups flour", 2.0, "cup"),
        ("1 tbsp olive oil", 1.0, "tbsp"),
        ("½ tsp salt", 0.5, "tsp"),
        ("8 oz cream cheese", 8.0, "oz"),
    ],
)
def test_english_grammar(line: str, qty: float, unit: str) -> None:
    parsed = parse(line)
    assert parsed.qty == qty
    assert parsed.unit == unit


# ─── awkward real lines ──────────────────────────────────────────────────


def test_a_parenthetical_is_a_note_not_a_quantity() -> None:
    parsed = parse("1 prk (400 g) tomaattimurskaa")
    assert parsed.qty == 1.0
    assert parsed.unit == "prk"
    assert parsed.note == "400 g"
    assert parsed.item == "tomaattimurskaa"


def test_a_line_with_no_quantity_still_parses() -> None:
    parsed = parse("suolaa ja pippuria")
    assert parsed.qty is None
    assert parsed.item == "suolaa ja pippuria"
    assert parsed.raw_text == "suolaa ja pippuria"


def test_raw_text_is_never_lost() -> None:
    """Whatever else fails, the author's own line survives verbatim."""
    for line in ("a pinch of salt", "??? mystery", "2 dl kermaa", ""):
        assert parse(line).raw_text == line


# ─── alternatives ────────────────────────────────────────────────────────


def test_tai_links_the_following_line() -> None:
    """kinuskikissa's "5 munan sokerikakkupohja TAI" / gluten-free variant.

    Two lines, one choice. Treating them as two ingredients makes a shopping
    list buy both.
    """
    lines = [
        "5 munan sokerikakkupohja TAI",
        "5 munan gluteeniton kakkupohja",
        "2 dl kermaa",
    ]
    assert alternative_positions(lines) == {1: 0}


def test_english_or_links_too() -> None:
    assert alternative_positions(["200 g butter or", "200 g margarine"]) == {1: 0}


def test_the_suffix_is_stripped_from_the_parsed_item() -> None:
    parsed = parse("5 munan sokerikakkupohja TAI")
    assert parsed.item is not None
    assert not parsed.item.endswith("TAI")
    # But the displayed line keeps it, because that is what the author wrote.
    assert parsed.raw_text.endswith("TAI")
