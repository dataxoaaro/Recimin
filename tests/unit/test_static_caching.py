"""Cache-Control on the statically served frontend.

These assert against a real built frontend/dist, so they skip when one is
absent — a backend-only checkout has nothing to serve.

The bug being guarded against was observed in production: with no Cache-Control
header from the origin, Cloudflare applied its own four-hour default and served
a superseded icon.svg with `cf-cache-status: HIT` half an hour after a deploy.
The same header on sw.js is worse than cosmetic, because browsers only bypass
the HTTP cache for a service worker when max-age exceeds 86400 — below that an
installed PWA keeps running the previous build until the cache expires.
"""

import re

import pytest
from fastapi.testclient import TestClient

from recimin.api.main import SPA_DIR

pytestmark = pytest.mark.skipif(
    not (SPA_DIR / "index.html").is_file(),
    reason="no built frontend to serve",
)

# Stable URLs whose contents change on deploy. Every one of these must be
# revalidated rather than served from a stale cache.
MUTABLE_PATHS = [
    "/",
    "/index.html",
    "/sw.js",
    "/registerSW.js",
    "/manifest.webmanifest",
    "/icon.svg",
    "/apple-touch-icon.png",
]


@pytest.mark.parametrize("path", MUTABLE_PATHS)
def test_stable_urls_must_revalidate(client: TestClient, path: str) -> None:
    response = client.get(path)
    if response.status_code == 404:
        pytest.skip(f"{path} not in this build")
    assert response.headers.get("cache-control") == "no-cache", (
        f"{path} carries no revalidation directive, so an intermediary is free "
        f"to serve a superseded copy after a deploy"
    )


def test_hashed_assets_are_immutable(client: TestClient) -> None:
    """Vite fingerprints /assets, so the contents behind a URL never change."""
    asset = re.search(r"/assets/[A-Za-z0-9._-]+\.js", client.get("/").text)
    assert asset, "no hashed asset referenced by index.html"

    cache_control = client.get(asset.group(0)).headers.get("cache-control", "")
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control


def test_the_apple_touch_icon_is_an_opaque_png(client: TestClient) -> None:
    """iOS ignores an SVG apple-touch-icon and composites alpha onto black.

    Colour type 2 is truecolour without an alpha channel; 6 is truecolour with
    one. The byte is at offset 25 of a PNG, in the IHDR chunk.
    """
    response = client.get("/apple-touch-icon.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"

    body = response.content
    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(body[16:20], "big")
    height = int.from_bytes(body[20:24], "big")
    assert (width, height) == (180, 180)
    assert body[25] == 2, "icon has an alpha channel; iOS would render it onto black"


def test_index_html_references_the_png_not_the_svg(client: TestClient) -> None:
    html = client.get("/").text
    link = re.search(r'<link rel="apple-touch-icon"[^>]*>', html)
    assert link, "no apple-touch-icon link"
    assert ".png" in link.group(0)
    assert ".svg" not in link.group(0)
