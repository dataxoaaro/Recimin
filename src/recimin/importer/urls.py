"""URL classification and normalisation.

Two jobs, and the order matters: redirects resolve *before* normalisation,
because `vm.tiktok.com/ZM8abc` and the canonical `tiktok.com/@user/video/123…`
are the same recipe and must collide on the dedupe index.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Stripped before the uniqueness check. Sharing the same reel from two places
# produces two different query strings and one recipe.
TRACKING_PARAMS = frozenset(
    {
        "igsh",
        "igshid",
        "fbclid",
        "gclid",
        "si",
        "_r",
        "_t",
        "share_id",
        "ref",
        "ref_src",
        "mibextid",
    }
)

INSTAGRAM_HOSTS = frozenset({"instagram.com", "instagr.am", "ig.me"})
TIKTOK_HOSTS = frozenset({"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"})
YOUTUBE_HOSTS = frozenset({"youtube.com", "youtu.be", "m.youtube.com"})

# A post, reel or TV item — anything with a shortcode.
_IG_POST = re.compile(r"^/(?:p|reel|reels|tv)/[^/]+/?$")
# A profile: a single path segment that is not a known non-profile route.
_IG_PROFILE = re.compile(r"^/([^/]+)/?$")
_IG_RESERVED = frozenset({"p", "reel", "reels", "tv", "explore", "accounts", "stories"})

_TT_VIDEO = re.compile(r"^/@[^/]+/video/\d+")
_TT_PHOTO = re.compile(r"^/@[^/]+/photo/\d+")
_TT_PROFILE = re.compile(r"^/@[^/]+/?$")
_TT_SHORT = re.compile(r"^/[A-Za-z0-9]+/?$")


class Platform(StrEnum):
    """Which extractor a URL routes to."""

    WEB = "web"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class UrlRejected(ValueError):
    """The URL is not importable, with a message meant for the user."""


@dataclass(frozen=True, slots=True)
class Classified:
    """A URL that passed classification."""

    platform: Platform
    normalised: str
    is_photo_post: bool = False
    needs_redirect_resolution: bool = False


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _registrable(host: str) -> str:
    """Strip a leading www. and nothing else. Not a full PSL implementation."""
    return host.removeprefix("www.").lower()


def normalise(url: str) -> str:
    """Canonical form for the dedupe index.

    Lowercases the host, drops the fragment, strips tracking parameters and
    removes a trailing slash. The path keeps its case: many CMSs are
    case-sensitive there.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"}:
        raise UrlRejected("Only http and https links can be imported")
    if not parts.hostname:
        raise UrlRejected("That does not look like a link")

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"

    return urlunsplit(
        ("https", parts.hostname.lower().removeprefix("www."), path, urlencode(kept), "")
    )


def classify(url: str) -> Classified:
    """Route a URL to an extractor, or reject it with a reason.

    Profiles and listing pages are rejected here, before any network request.
    Enumerating a profile is the pattern that gets a residential IP throttled,
    and it is not what "share this recipe" means.
    """
    normalised = normalise(url)
    parts = urlsplit(normalised)
    host = _registrable(parts.hostname or "")
    path = parts.path

    if host in INSTAGRAM_HOSTS:
        if _IG_POST.match(path):
            return Classified(Platform.INSTAGRAM, normalised)
        match = _IG_PROFILE.match(path)
        if match and match.group(1) not in _IG_RESERVED:
            raise UrlRejected("Share an individual post, not a profile")
        raise UrlRejected("That Instagram link is not a post")

    if host in TIKTOK_HOSTS:
        if host in {"vm.tiktok.com", "vt.tiktok.com"} or _TT_SHORT.match(path):
            # A short link hides its real shape until it is followed.
            return Classified(Platform.TIKTOK, normalised, needs_redirect_resolution=True)
        if _TT_PHOTO.match(path):
            return Classified(Platform.TIKTOK, normalised, is_photo_post=True)
        if _TT_VIDEO.match(path):
            return Classified(Platform.TIKTOK, normalised)
        if _TT_PROFILE.match(path):
            raise UrlRejected("Share an individual post, not a profile")
        raise UrlRejected("That TikTok link is not a post")

    if host in YOUTUBE_HOSTS:
        return Classified(Platform.YOUTUBE, normalised)

    if path in {"/", ""}:
        raise UrlRejected("No recipe found on this page. Share a specific recipe instead.")

    return Classified(Platform.WEB, normalised)
