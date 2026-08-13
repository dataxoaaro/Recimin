"""Web page extraction.

Generic by construction: schema.org is a universal standard, so this path needs
no per-site adapters. Measured, it produced complete structured data on 30 of 34
tested pages including all eight Finnish sites, with zero site-specific code.

The fetch layer carries two hard-won rules, both in Appendix A:

  1. HTTP/1.1, never HTTP/2. Same IP, same UA, protocol the only variable:
     allrecipes 402 -> 200, seriouseats 402 -> 200, k-ruoka 403 -> 200.
     httpx defaults to 1.1; the entire mitigation is not opting in.
  2. Parse microdata and RDFa alongside JSON-LD. smittenkitchen — a top-tier
     recipe blog — has zero JSON-LD and complete microdata.
"""

import json
import logging
from typing import Any

import extruct
import httpx
from selectolax.parser import HTMLParser

from recimin.config import Settings
from recimin.importer.normalise import NormalisedRecipe, from_schema_org

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0, connect=10.0)
RETRY_STATUSES = frozenset({402, 403, 406, 429})
SYNTAXES = ["json-ld", "microdata", "rdfa"]


class FetchFailed(Exception):
    """The page could not be retrieved."""


class NoRecipeFound(Exception):
    """The page was retrieved but carries no Recipe.

    Carries the readable page text so the caller can decide whether to spend an
    LLM call on it rather than re-fetching.
    """

    def __init__(self, message: str, *, page_text: str = "") -> None:
        super().__init__(message)
        self.page_text = page_text


def build_headers(settings: Settings) -> dict[str, str]:
    """Browser-shaped headers, plus honest do-not-track signals.

    DNT and Sec-GPC rather than a synthesised consent cookie: forging consent
    asserts a choice the user never made, and it was measured to change nothing
    — six CMPs returned byte-identical responses with and without one.
    """
    return {
        "User-Agent": settings.scraper_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Sec-GPC": "1",
    }


def fetch(url: str, settings: Settings) -> str:
    """Retrieve a page as HTML.

    Explicitly http1-only. Passing http2=True here is the single change most
    likely to turn a working import into a 402.
    """
    try:
        with httpx.Client(
            http2=False,
            follow_redirects=True,
            timeout=TIMEOUT,
            headers=build_headers(settings),
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        raise FetchFailed(f"{type(error).__name__}: {error}") from error

    if response.status_code in RETRY_STATUSES:
        raise FetchFailed(f"HTTP {response.status_code} (bot protection)")
    if response.status_code >= 400:
        raise FetchFailed(f"HTTP {response.status_code}")
    return response.text


def iter_nodes(data: Any) -> Any:
    """Walk every dict in an arbitrarily nested structure."""
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from iter_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from iter_nodes(item)


def is_recipe(node: dict[str, Any]) -> bool:
    """Whether a node is a schema.org Recipe, in any @type shape."""
    node_type = node.get("@type") or node.get("type") or ""
    types = node_type if isinstance(node_type, list) else [node_type]
    return any(
        isinstance(entry, str) and entry.rstrip("/").rsplit("/", 1)[-1] == "Recipe"
        for entry in types
    )


def find_recipe_node(html: str, url: str) -> dict[str, Any] | None:
    """Locate the Recipe node in a page's structured data.

    Walks the whole graph rather than checking the root. A root-level equality
    check silently loses k-ruoka (nested under WebPage.mainEntity) and
    daskochrezept (wrapped in @graph).
    """
    try:
        data = extruct.extract(html, base_url=url, syntaxes=SYNTAXES, uniform=True)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        logger.warning("structured data parse failed", extra={"url": url, "error": str(error)})
        return None

    for node in iter_nodes(data):
        if is_recipe(node):
            return node
    return None


def readable_text(html: str, limit: int = 12_000) -> str:
    """Strip a page to its visible text, for the LLM fallback in Phase 8."""
    tree = HTMLParser(html)
    for tag in ("script", "style", "nav", "header", "footer", "noscript", "svg"):
        for node in tree.css(tag):
            node.decompose()
    body = tree.body
    return (body.text(separator="\n", strip=True) if body else "")[:limit]


def from_recipe_scrapers(html: str, url: str) -> NormalisedRecipe | None:
    """Second opinion from recipe-scrapers, in wild mode.

    It carries 728 site-specific adapters, none of them for a .fi domain — so
    this does nothing for the Finnish path and exists purely for the English
    long tail. Its own generic fallback is roughly what we already do, so this
    only ever helps on a site it has an adapter for.

    Never use its to_json(): every field is wrapped in a bare `except: pass`,
    so it silently omits keys. And never its yields(): it Anglicises the unit,
    turning "4-6 annosta" into "4 servings".
    """
    try:
        from recipe_scrapers import scrape_html
    except ImportError:  # pragma: no cover - dependency is declared
        return None

    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception as error:
        logger.info("recipe-scrapers declined", extra={"url": url, "error": str(error)[:200]})
        return None

    def attempt(name: str) -> object:
        """Every getter can raise; a missing field is not a failure."""
        try:
            return getattr(scraper, name)()
        except Exception:
            return None

    ingredients = attempt("ingredients") or []
    instructions = attempt("instructions") or ""
    title = attempt("title") or ""
    if not (title and (ingredients or instructions)):
        return None

    from recimin.importer.normalise import clean_text, clean_title

    steps = [clean_text(line) for line in str(instructions).split("\n") if clean_text(line)]
    return NormalisedRecipe(
        title=clean_title(title),
        ingredients=[clean_text(line) for line in ingredients if clean_text(line)],
        instructions_md="\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)),
        total_time_minutes=attempt("total_time") or None,
        image_url=attempt("image") or None,
        author=attempt("author") or None,
    )


def extract(url: str, settings: Settings) -> NormalisedRecipe:
    """Fetch a page and pull a recipe out of it.

    Tiered, cheapest first:
      1. schema.org via extruct — covers 30 of 34 tested pages
      2. recipe-scrapers, for the English long tail
      3. give up, with the readable text attached for the LLM to try

    Raises NoRecipeFound when nothing works. For a listing page like
    valio.fi/reseptihaku/ or a site root, that is the correct outcome, and the
    exception carries the page text so the caller can decide whether to spend
    an LLM call on it.
    """
    html = fetch(url, settings)

    node = find_recipe_node(html, url)
    recipe = from_schema_org(node) if node is not None else None

    if recipe is None or not recipe.is_usable:
        fallback = from_recipe_scrapers(html, url)
        if fallback is not None and fallback.is_usable:
            logger.info("recipe-scrapers supplied the recipe", extra={"url": url})
            recipe = fallback

    if recipe is None or not recipe.is_usable:
        raise NoRecipeFound(
            "No recipe found on this page. Share a specific recipe instead.",
            page_text=readable_text(html),
        )

    logger.info(
        "web recipe extracted",
        extra={"url": url, "ingredients": len(recipe.ingredients), "title": recipe.title},
    )
    return recipe
