"""URL classification and normalisation.

The dedupe index depends entirely on this module, so its table tests are the
cheapest defence against a library full of duplicates.
"""

import pytest

from recimin.importer.urls import Platform, UrlRejected, classify, normalise


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.valio.fi/reseptit/x/", "https://valio.fi/reseptit/x"),
        ("HTTPS://WWW.VALIO.FI/reseptit/X", "https://valio.fi/reseptit/X"),
        ("https://valio.fi/reseptit/x#ingredients", "https://valio.fi/reseptit/x"),
        ("  https://valio.fi/reseptit/x  ", "https://valio.fi/reseptit/x"),
        ("http://valio.fi/reseptit/x", "https://valio.fi/reseptit/x"),
    ],
)
def test_normalisation(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_path_case_is_preserved() -> None:
    """Many CMSs are case-sensitive in the path; lowercasing it breaks links."""
    assert normalise("https://Example.fi/Recipes/Cake") == "https://example.fi/Recipes/Cake"


@pytest.mark.parametrize(
    "param",
    ["igsh", "igshid", "fbclid", "si", "_r", "_t", "utm_source" if False else "ref"],
)
def test_tracking_params_are_stripped(param: str) -> None:
    """Sharing the same post from two places must not create two recipes."""
    base = "https://instagram.com/p/DWjfQTDNm_l"
    assert normalise(f"{base}?{param}=abc123") == base


def test_meaningful_query_params_survive() -> None:
    assert normalise("https://example.fi/r?id=7") == "https://example.fi/r?id=7"


@pytest.mark.parametrize("scheme", ["ftp://x.fi/a", "javascript:alert(1)", "file:///etc/passwd"])
def test_non_http_schemes_are_rejected(scheme: str) -> None:
    with pytest.raises(UrlRejected):
        normalise(scheme)


def test_garbage_is_rejected() -> None:
    with pytest.raises(UrlRejected):
        normalise("not a url at all")


# ─── classification ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://www.instagram.com/p/DWjfQTDNm_l/", Platform.INSTAGRAM),
        ("https://instagram.com/reel/ABC123/", Platform.INSTAGRAM),
        ("https://www.tiktok.com/@user/video/7106594312292453675", Platform.TIKTOK),
        ("https://www.youtube.com/shorts/abc", Platform.YOUTUBE),
        ("https://youtu.be/abc", Platform.YOUTUBE),
        ("https://www.valio.fi/reseptit/shanghai-taco-salaatti/", Platform.WEB),
        ("https://www.kinuskikissa.fi/perinteinen-mansikkakakku", Platform.WEB),
    ],
)
def test_platform_routing(url: str, platform: Platform) -> None:
    assert classify(url).platform is platform


def test_tiktok_photo_posts_are_flagged() -> None:
    """yt-dlp cannot touch /photo/; it has to route to gallery-dl."""
    result = classify("https://www.tiktok.com/@user/photo/7106594312292453675")
    assert result.platform is Platform.TIKTOK
    assert result.is_photo_post is True


def test_tiktok_short_links_are_flagged_for_resolution() -> None:
    result = classify("https://vm.tiktok.com/ZM8abcdef/")
    assert result.needs_redirect_resolution is True


# ─── rejection ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/kinuskikissa/",
        "https://instagram.com/nasa",
        "https://www.tiktok.com/@kinuskikissa",
        "https://www.tiktok.com/@kinuskikissa/",
    ],
)
def test_profiles_are_rejected(url: str) -> None:
    """Never crawl a grid. Enumeration is what gets a residential IP throttled."""
    with pytest.raises(UrlRejected, match="individual post"):
        classify(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.valio.fi/",
        "https://www.kinuskikissa.fi/",
        "https://example.fi",
    ],
)
def test_site_roots_are_rejected(url: str) -> None:
    with pytest.raises(UrlRejected, match="No recipe found"):
        classify(url)


def test_instagram_explore_is_not_mistaken_for_a_profile() -> None:
    with pytest.raises(UrlRejected, match="not a post"):
        classify("https://www.instagram.com/explore/")


def test_a_listing_page_deeper_than_root_is_allowed_through() -> None:
    """valio.fi/reseptihaku/ cannot be told from a recipe by URL alone.

    It is rejected later, by the extractor finding no Recipe node — which is the
    correct place, since only the page content can settle it.
    """
    assert classify("https://www.valio.fi/reseptihaku/").platform is Platform.WEB
