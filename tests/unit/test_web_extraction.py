"""Web extraction, against real pages saved from a Finnish residential IP.

Fixtures rather than live fetches, so the suite does not depend on a site
staying up or unchanged. The live check is marked and excluded by default.
"""

from pathlib import Path

import pytest

from recimin.config import Settings
from recimin.importer import web
from recimin.importer.normalise import (
    clean_text,
    clean_title,
    flatten_instructions,
    parse_duration,
    parse_yield,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pages"
SETTINGS_OK = Settings(jwt_secret="x" * 32, site_password="site-password")


def load(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8", errors="replace")


# ─── the normaliser ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "minutes"),
    [
        ("PT15M", 15),
        ("PT3H", 180),
        ("PT1H30M", 90),
        ("P0DT5H30M", 330),
        # Every one of these appeared on a live Finnish page.
        ("PT", None),
        ("PTM", None),
        ("PT0M", None),
        ("", None),
        (None, None),
        ("not a duration", None),
    ],
)
def test_duration_parsing(raw: str | None, minutes: int | None) -> None:
    assert parse_duration(raw) == minutes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2, 2 annosta", (2, "2 annosta")),
        ("4-6 annosta", (4, "4-6 annosta")),
        ("4–6 annosta", (4, "4–6 annosta")),
        ("15", (15, None)),
        ("10 palaa", (10, "10 palaa")),
        ("1 pelti", (1, "1 pelti")),
        (["4 annosta"], (4, "4 annosta")),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_yield_parsing(raw: object, expected: tuple[int | None, str | None]) -> None:
    """The Finnish unit word must survive. recipe-scrapers throws it away."""
    assert parse_yield(raw) == expected


def test_nbsp_and_double_spaces_collapse() -> None:
    assert clean_text("5\xa0 munan  sokerikakkupohja") == "5 munan sokerikakkupohja"


def test_seo_suffix_is_stripped() -> None:
    assert clean_title("Mustikkapiirakka – katso ohje! | Maku") == "Mustikkapiirakka"
    # A title that is mostly suffix must not be reduced to nothing.
    assert clean_title("Kakku") == "Kakku"


def test_howto_sections_are_unwrapped() -> None:
    """arla nests steps one level deeper than everyone else."""
    steps = flatten_instructions(
        [
            {
                "@type": "HowToSection",
                "itemListElement": [
                    {"@type": "HowToStep", "text": "Heat the oven."},
                    {"@type": "HowToStep", "text": "Mix the flour."},
                ],
            }
        ]
    )
    assert steps == ["Heat the oven.", "Mix the flour."]


def test_bullet_prefixes_are_stripped() -> None:
    """kotikokki ships literal '- ' inside its step text."""
    assert flatten_instructions(["- Heat the oven."]) == ["Heat the oven."]
    assert flatten_instructions(["1. Heat the oven."]) == ["Heat the oven."]


def test_instruction_arrays_are_joined_before_splitting() -> None:
    """myllynparas splits one sentence across two array entries.

    Splitting each entry independently would produce two nonsense fragments.
    """
    steps = flatten_instructions(["Lisää sokeri ja vatkaa", "kunnes seos on vaaleaa."])
    assert len(steps) == 1
    assert steps[0] == "Lisää sokeri ja vatkaa kunnes seos on vaaleaa."


# ─── the SSRF guard ──────────────────────────────────────────────────────


def _resolver(mapping: dict[str, str]):
    """A fake getaddrinfo: named hosts resolve per the mapping, IP literals
    resolve to themselves."""

    def resolve(host: str, *args: object, **kwargs: object):
        address = mapping.get(host, host)
        return [(2, 1, 6, "", (address, 0))]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://192.168.1.1/router",
        "http://10.0.0.5/x",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_private_addresses_are_refused(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker lives on the household LAN; an import must never become a
    probe of it."""
    monkeypatch.setattr(web.socket, "getaddrinfo", _resolver({}))
    with pytest.raises(web.FetchFailed, match="non-public"):
        web._reject_non_public_host(url)


def test_a_hostname_resolving_privately_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.socket, "getaddrinfo", _resolver({"innocent.example": "192.168.0.50"}))
    with pytest.raises(web.FetchFailed, match="non-public"):
        web._reject_non_public_host("https://innocent.example/recipe")


def test_a_redirect_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """follow_redirects=True would only guard the first hop; every hop must
    pass."""
    import httpx

    monkeypatch.setattr(web.socket, "getaddrinfo", _resolver({"public.example": "93.184.216.34"}))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://192.168.1.1/router"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    with pytest.raises(web.FetchFailed, match="non-public"):
        web._guarded_get(client, "https://public.example/recipe")


def test_a_public_redirect_chain_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(
        web.socket,
        "getaddrinfo",
        _resolver({"public.example": "93.184.216.34", "cdn.example": "93.184.216.35"}),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(301, headers={"Location": "https://cdn.example/page"})
        return httpx.Response(200, text="<html>ok</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    response = web._guarded_get(client, "https://public.example/recipe")
    assert response.status_code == 200
    assert response.text == "<html>ok</html>"


def test_recipe_category_is_carried_through() -> None:
    """recipeCategory ships as a string or a list; either way persist() gets to
    see it rather than defaulting every import to dinner."""
    from recimin.importer.normalise import from_schema_org

    node = {"@type": "Recipe", "name": "Kakku", "recipeIngredient": ["2 dl kermaa"]}
    assert from_schema_org({**node, "recipeCategory": "Dessert"}).category == "Dessert"
    assert from_schema_org({**node, "recipeCategory": ["Jälkiruoat"]}).category == "Jälkiruoat"
    assert from_schema_org(node).category is None


# ─── real pages ──────────────────────────────────────────────────────────


def test_valio_recipe() -> None:
    node = web.find_recipe_node(load("valio_shanghai_taco_salaatti"), "https://valio.fi/x")
    assert node is not None

    from recimin.importer.normalise import from_schema_org

    recipe = from_schema_org(node)
    assert recipe.title == "Shanghai taco -salaatti"
    assert len(recipe.ingredients) == 10
    assert recipe.ingredients[0].startswith("1 pkt")
    assert recipe.total_time_minutes == 15
    assert recipe.servings == 2
    assert recipe.yield_text == "2 annosta"
    assert recipe.language == "fi"
    assert recipe.author == "Oona Heikkinen"
    assert recipe.is_usable


def test_kinuskikissa_recipe() -> None:
    """A site recipe-scrapers has no adapter for. It needs none."""
    node = web.find_recipe_node(load("kinuskikissa_mansikkakakku"), "https://kinuskikissa.fi/x")
    assert node is not None

    from recimin.importer.normalise import from_schema_org

    recipe = from_schema_org(node)
    assert recipe.title == "Perinteinen mansikkakakku"
    # The page ships 20 recipeIngredient entries, one of which is "   ".
    # Dropping the blank is correct; carrying it would render an empty bullet.
    assert len(recipe.ingredients) == 19
    # recipeYield is the bare integer "15" — a servings count with no unit word.
    assert recipe.servings == 15
    assert recipe.yield_text is None
    # prepTime is "PT0M" and cookTime "PT3H"; PT0M must not poison the sum.
    assert recipe.total_time_minutes == 180
    assert recipe.language == "fi"
    assert recipe.is_usable


def test_kinuskikissa_double_spaces_are_cleaned() -> None:
    from recimin.importer.normalise import from_schema_org

    node = web.find_recipe_node(load("kinuskikissa_mansikkakakku"), "https://kinuskikissa.fi/x")
    assert node is not None
    for line in from_schema_org(node).ingredients:
        assert "  " not in line
        assert "\xa0" not in line


def test_the_tai_alternative_survives_verbatim() -> None:
    """One choice split across two lines. Raw text must not be mangled."""
    from recimin.importer.normalise import from_schema_org

    node = web.find_recipe_node(load("kinuskikissa_mansikkakakku"), "https://kinuskikissa.fi/x")
    assert node is not None
    lines = from_schema_org(node).ingredients
    assert any(line.rstrip().endswith("TAI") for line in lines)


@pytest.mark.parametrize("fixture", ["valio_reseptihaku_listing", "kinuskikissa_home"])
def test_listing_pages_yield_no_recipe(fixture: str) -> None:
    """valio's search page has WebSite+SearchAction; kinuskikissa's home has no
    ld+json at all. Both must fail cleanly rather than crash."""
    assert web.find_recipe_node(load(fixture), "https://example.fi/") is None


def test_extract_raises_a_user_facing_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "fetch", lambda url, settings: load("kinuskikissa_home"))
    with pytest.raises(web.NoRecipeFound, match="No recipe found"):
        web.extract(
            "https://kinuskikissa.fi/", Settings(jwt_secret="x" * 32, site_password="site-password")
        )


def test_readable_text_drops_scripts() -> None:
    text = web.readable_text(load("kinuskikissa_mansikkakakku"))
    assert "function" not in text.lower()[:2000]
    assert len(text) > 200


# ─── fetch configuration ─────────────────────────────────────────────────


def test_headers_are_browser_shaped_and_honest() -> None:
    settings = Settings(jwt_secret="x" * 32, site_password="site-password")
    headers = web.build_headers(settings)
    assert "Chrome/" in headers["User-Agent"]
    assert headers["Accept-Language"].startswith("fi-FI")
    # Honest signals rather than a forged consent cookie, which was measured to
    # change nothing on six different CMPs.
    assert headers["DNT"] == "1"
    assert headers["Sec-GPC"] == "1"


def test_fetch_never_negotiates_http2() -> None:
    """The single highest-value line in the fetch layer.

    Measured: allrecipes 402 on h2 and 200 on 1.1, same IP, same UA.
    """
    import inspect

    source = inspect.getsource(web.fetch)
    assert "http2=False" in source
    # Only the docstring may mention the opposite.
    code = source.split('"""')[-1]
    assert "http2=True" not in code


# ─── live ────────────────────────────────────────────────────────────────


@pytest.mark.live
@pytest.mark.parametrize(
    ("url", "title"),
    [
        (
            "https://www.valio.fi/reseptit/shanghai-taco-salaatti/",
            "Shanghai taco -salaatti",
        ),
        (
            "https://www.kinuskikissa.fi/perinteinen-mansikkakakku",
            "Perinteinen mansikkakakku",
        ),
    ],
)
def test_live_fetch_still_passes_bot_protection(url: str, title: str) -> None:
    """Confirms HTTP/1.1 still gets through. Run with: pytest -m live"""
    settings = Settings(jwt_secret="x" * 32, site_password="site-password")
    recipe = web.extract(url, settings)
    assert recipe.title == title
    assert recipe.ingredients


# ─── the fallback chain ──────────────────────────────────────────────────


def test_recipe_scrapers_is_tried_when_schema_org_finds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from recimin.importer.normalise import NormalisedRecipe

    monkeypatch.setattr(web, "fetch", lambda url, s: "<html><body>prose</body></html>")
    monkeypatch.setattr(web, "find_recipe_node", lambda html, url: None)
    monkeypatch.setattr(
        web,
        "from_recipe_scrapers",
        lambda html, url: NormalisedRecipe(title="From the adapter", ingredients=["2 dl kermaa"]),
    )

    recipe = web.extract("https://allrecipes.com/x", SETTINGS_OK)
    assert recipe.title == "From the adapter"


def test_no_recipe_found_carries_the_page_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """So the caller can spend one LLM call on it without re-fetching."""
    monkeypatch.setattr(web, "fetch", lambda url, s: load("kinuskikissa_home"))
    monkeypatch.setattr(web, "find_recipe_node", lambda html, url: None)
    monkeypatch.setattr(web, "from_recipe_scrapers", lambda html, url: None)

    with pytest.raises(web.NoRecipeFound) as caught:
        web.extract("https://kinuskikissa.fi/", SETTINGS_OK)
    assert len(caught.value.page_text) > 200


def test_recipe_scrapers_failure_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every one of its getters can raise. A missing field is not a failure."""
    assert web.from_recipe_scrapers("<html></html>", "https://x.fi/a") is None
