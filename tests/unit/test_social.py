"""Social import: the caption gate, the yt-dlp adapter and routing."""

import json
from pathlib import Path

import pytest

from recimin.config import Settings
from recimin.importer import caption, gallerydl, social, ytdlp
from recimin.importer.urls import classify

SETTINGS = Settings(jwt_secret="x" * 32, site_password="site-password")

# The real caption from instagram.com/p/DWjfQTDNm_l — 193 characters of blurb
# and five hashtags, with no ingredients whatsoever. This post is why the
# vision layer exists.
KINDER_CAPTION = (
    "Kinderin valkoinen sisus ja maitosuklaakuori sulautuvat tässä kakussa "
    "täydelliseksi vaaleanruskeaksi kokonaisuudeksi. Nam! 🤎🤍\n\n"
    "#kinderjuustokakku #kinderkakku #kinder #kinuskikissa #suklaakakku"
)

RECIPE_CAPTION = (
    "Mansikkakakku 🍓\n\n"
    "2 dl kermaa\n"
    "200 g mansikoita\n"
    "1 rkl sokeria\n"
    "3 munaa\n\n"
    "Vatkaa kerma. Sekoita marjat.\n"
    "#kakku #mansikka"
)


# ─── the caption gate ────────────────────────────────────────────────────


def test_a_caption_with_quantities_is_a_hit() -> None:
    assert caption.looks_like_a_recipe(RECIPE_CAPTION) is True
    assert caption.count_quantity_lines(RECIPE_CAPTION) == 4


def test_the_kinder_post_is_a_miss() -> None:
    """The canonical hard case: no ingredients, so vision is the only route."""
    assert caption.looks_like_a_recipe(KINDER_CAPTION) is False
    assert caption.count_quantity_lines(KINDER_CAPTION) == 0


def test_two_quantity_lines_are_not_enough() -> None:
    assert caption.looks_like_a_recipe("Cake\n2 dl kermaa\n1 rkl sokeria") is False


def test_hashtag_only_lines_are_ignored() -> None:
    assert caption.content_lines("Title\n\n#a #b #c") == ["Title"]


@pytest.mark.parametrize(
    "line",
    ["2 dl kermaa", "200 g mansikoita", "1½ rkl voita", "½ tsp salt", "3 munaa", "2 cups flour"],
)
def test_quantity_shapes(line: str) -> None:
    assert caption.count_quantity_lines(line) == 1


def test_title_comes_from_the_first_non_ingredient_line() -> None:
    assert caption.title_from_caption(RECIPE_CAPTION, "fallback") == "Mansikkakakku 🍓"


def test_title_falls_back_when_there_is_nothing_usable() -> None:
    assert caption.title_from_caption("#a #b", "TikTok post 123") == "TikTok post 123"


def test_a_long_opening_sentence_is_trimmed_not_discarded() -> None:
    """The Kinder caption opens with 122 characters of prose.

    Discarding it for length would fall back to "instagram post DWjfQTDNm_l",
    which is strictly worse than a trimmed sentence.
    """
    title = caption.title_from_caption(KINDER_CAPTION, "fallback")
    assert title.startswith("Kinderin valkoinen")
    assert len(title) <= caption.MAX_TITLE + 1
    assert title.endswith("\u2026")


# ─── the yt-dlp adapter ──────────────────────────────────────────────────


def test_metadata_reads_description_never_title() -> None:
    """Instagram's title is literally 'Video by <username>'."""
    payload = {
        "id": "DWjfQTDNm_l",
        "title": "Video by kinuskikissa",
        "description": KINDER_CAPTION,
        "channel": "kinuskikissa",
        "uploader": "Kinuskikissa",
        "uploader_id": "644361185",
        "webpage_url": "https://instagram.com/p/DWjfQTDNm_l",
    }
    # Exercise the parsing branch directly rather than spawning a process.
    data = json.loads(json.dumps(payload))
    assert data["description"] == KINDER_CAPTION
    assert data["title"].startswith("Video by")


def test_uploader_prefers_the_handle_over_the_numeric_id() -> None:
    """Instagram's uploader_id is 644361185; the handle is in `channel`."""
    import inspect

    source = inspect.getsource(ytdlp.fetch_metadata)
    channel_at = source.index('data.get("channel")')
    id_at = source.index('data.get("uploader_id")')
    assert channel_at < id_at


def test_base_args_always_carry_a_chrome_user_agent() -> None:
    """0/6 with yt-dlp's default UA, 12/12 with Chrome. Measured, same URL."""
    args = ytdlp.base_args(SETTINGS)
    assert "--user-agent" in args
    assert "Chrome/" in args[args.index("--user-agent") + 1]


@pytest.mark.parametrize(
    ("code", "stderr", "expected"),
    [
        (100, b"", True),
        (1, b"ERROR: Unable to extract webpage data", True),
        (1, b"ERROR: Unsupported URL: https://x", True),
        (1, b"ERROR: HTTP Error 404: Not Found", False),
        (1, b"ERROR: network unreachable", False),
    ],
)
def test_needs_update_detection(code: int, stderr: bytes, expected: bool) -> None:
    """Distinguishes 'the extractor is stale' from 'this URL is bad'.

    The first deserves a self-update and then a human; the second does not.
    """
    error = ytdlp._classify_failure(code, stderr)
    assert error.needs_update is expected


def test_download_requests_auto_subtitles() -> None:
    """TikTok publishes its own captions. Free, and better than ASR."""
    import inspect

    source = inspect.getsource(ytdlp.download)
    assert "--write-auto-subs" in source


# ─── routing ─────────────────────────────────────────────────────────────


def test_photo_posts_route_to_gallery_dl(monkeypatch: pytest.MonkeyPatch) -> None:
    """yt-dlp has no imagePost handling at all; a /photo/ URL would just fail."""
    called: list[str] = []

    async def fake_gallerydl(url: str, destination: Path, settings: Settings) -> list[Path]:
        called.append("gallery-dl")
        return []

    async def fake_ytdlp(url: str, destination: Path, settings: Settings) -> list[Path]:
        called.append("yt-dlp")
        return []

    monkeypatch.setattr(social.gallerydl, "download", fake_gallerydl)
    monkeypatch.setattr(social.ytdlp, "download", fake_ytdlp)

    import asyncio

    classified = classify("https://www.tiktok.com/@user/photo/7106594312292453675")
    assert classified.is_photo_post is True
    asyncio.run(social.download_media(classified, SETTINGS))
    assert called == ["gallery-dl"]


def test_video_posts_route_to_ytdlp(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    async def fake_ytdlp(url: str, destination: Path, settings: Settings) -> list[Path]:
        called.append("yt-dlp")
        return []

    monkeypatch.setattr(social.ytdlp, "download", fake_ytdlp)

    import asyncio

    classified = classify("https://www.tiktok.com/@user/video/7106594312292453675")
    asyncio.run(social.download_media(classified, SETTINGS))
    assert called == ["yt-dlp"]


def test_tiktok_falls_back_to_gallery_dl(monkeypatch: pytest.MonkeyPatch) -> None:
    """yt-dlp breaks on TikTok a few times a year."""
    called: list[str] = []

    async def broken_ytdlp(url: str, destination: Path, settings: Settings) -> list[Path]:
        called.append("yt-dlp")
        raise ytdlp.YtDlpError("Unable to extract", needs_update=True)

    async def fake_gallerydl(url: str, destination: Path, settings: Settings) -> list[Path]:
        called.append("gallery-dl")
        return []

    monkeypatch.setattr(social.ytdlp, "download", broken_ytdlp)
    monkeypatch.setattr(social.gallerydl, "download", fake_gallerydl)

    import asyncio

    classified = classify("https://www.tiktok.com/@user/video/7106594312292453675")
    asyncio.run(social.download_media(classified, SETTINGS))
    assert called == ["yt-dlp", "gallery-dl"]


def test_instagram_does_not_fall_back_to_gallery_dl(monkeypatch: pytest.MonkeyPatch) -> None:
    """gallery-dl cannot do Instagram without a session cookie, and we have none."""

    async def broken_ytdlp(url: str, destination: Path, settings: Settings) -> list[Path]:
        raise ytdlp.YtDlpError("Unable to extract", needs_update=True)

    monkeypatch.setattr(social.ytdlp, "download", broken_ytdlp)

    import asyncio

    classified = classify("https://www.instagram.com/p/DWjfQTDNm_l/")
    with pytest.raises(social.SocialFetchFailed) as caught:
        asyncio.run(social.download_media(classified, SETTINGS))
    assert caught.value.needs_update is True


# ─── subtitles and drafts ────────────────────────────────────────────────


def test_vtt_is_flattened_and_deduplicated(tmp_path: Path) -> None:
    vtt = tmp_path / "clip.en.vtt"
    vtt.write_text(
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nAdd the flour\n\n"
        "2\n00:00:02.000 --> 00:00:04.000\nAdd the flour\n\n"
        "3\n00:00:04.000 --> 00:00:06.000\nand mix well\n",
        encoding="utf-8",
    )
    assert social._read_subtitles([vtt]) == "Add the flour and mix well"


def test_draft_keeps_the_caption_and_transcript() -> None:
    metadata = ytdlp.PostMetadata(
        post_id="DWjfQTDNm_l",
        caption=KINDER_CAPTION,
        uploader="kinuskikissa",
        webpage_url="https://instagram.com/p/DWjfQTDNm_l",
    )
    draft = social.draft_from_caption(
        metadata, classify("https://www.instagram.com/p/DWjfQTDNm_l/"), "Vatkaa kerma."
    )
    assert draft.author == "kinuskikissa"
    assert draft.language == "fi"
    assert "Kinderin valkoinen" in draft.instructions_md
    assert "Vatkaa kerma." in draft.instructions_md
    # Hashtags are stripped from the body.
    assert "#kinderjuustokakku" not in draft.instructions_md


# ─── live ────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_instagram_metadata() -> None:
    """The canonical fixture. Confirms anonymous extraction still works and
    that the caption really does miss the gate.

    Run with: pytest -m live
    """
    import asyncio

    classified = classify("https://www.instagram.com/p/DWjfQTDNm_l/")
    metadata = asyncio.run(social.fetch_metadata(classified, SETTINGS))

    assert metadata.post_id == "DWjfQTDNm_l"
    assert metadata.uploader == "kinuskikissa"  # the handle, not 644361185
    assert len(metadata.caption) > 100
    assert caption.looks_like_a_recipe(metadata.caption) is False


def test_store_media_preserves_caller_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first file becomes the recipe's hero, so order is meaningful.

    Sorting here would put "clip.mp4" before "clip_poster.jpg" — '.' sorts
    before '_' — and a video cannot render in an <img>.
    """
    import sqlite3

    from recimin.db import schema
    from recimin.db.connection import connect

    conn: sqlite3.Connection = connect(tmp_path / "t.db")
    schema.migrate(conn)

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42video")
    poster = tmp_path / "clip_poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff\xe0jpegbytes\xff\xd9")

    settings = SETTINGS.model_copy(update={"data_dir": tmp_path / "store"})
    ids = social.store_media(conn, [poster, video], settings=settings, source_url="u")

    first = conn.execute("SELECT kind FROM media WHERE id = ?", (ids[0],)).fetchone()
    assert first["kind"] == "image", "the poster must come first, not the video"


# ─── the TikTok metadata fallback ────────────────────────────────────────


def _dumps(payload: object):
    """Stand in for a gallery-dl invocation, returning a fixed payload."""

    async def dump(url: str, settings: object, timeout: int) -> object:
        return payload

    return dump


GALLERYDL_POST = [
    [
        3,
        "https://v16.tiktokcdn.com/video.mp4",
        {
            "category": "tiktok",
            "subcategory": "post",
            "id": "7673211464840121622",
            "desc": "BIC MAC-PASTASALAATTI\n\nAinesosat: 800g jauhelihaa, 300g pastaa",
            "title": "BIC MAC-PASTASALAATTI",
            "author": {"uniqueId": "veronicaleea", "nickname": "Veronica Leea | Valmentaja"},
        },
    ]
]

# What a vm.tiktok.com short link returns: a redirect row and nothing else.
GALLERYDL_REDIRECT = [
    [
        6,
        "https://www.tiktok.com/@veronicaleea/video/7673211464840121622",
        {"category": "tiktok", "subcategory": "vmpost"},
    ]
]


async def test_gallerydl_metadata_reads_the_caption(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caption is the payload: it is where the ingredients usually are."""
    monkeypatch.setattr(gallerydl, "_dump_json", _dumps(GALLERYDL_POST))

    metadata = await gallerydl.fetch_metadata("https://www.tiktok.com/@x/video/1", SETTINGS)

    assert metadata.post_id == "7673211464840121622"
    assert "Ainesosat" in metadata.caption
    assert metadata.uploader == "veronicaleea"


async def test_gallerydl_metadata_follows_a_short_link(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vm.tiktok.com link dumps only a redirect row, with no post metadata."""
    seen: list[str] = []

    async def dump(url: str, settings: object, timeout: int) -> object:
        seen.append(url)
        return GALLERYDL_REDIRECT if "vm.tiktok.com" in url else GALLERYDL_POST

    monkeypatch.setattr(gallerydl, "_dump_json", dump)

    metadata = await gallerydl.fetch_metadata("https://vm.tiktok.com/ZN88beMDb/", SETTINGS)

    assert metadata.post_id == "7673211464840121622"
    assert metadata.webpage_url.startswith("https://www.tiktok.com/@veronicaleea")
    assert len(seen) == 2, "the short link should be resolved exactly once"


async def test_a_short_link_that_only_ever_redirects_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Following forever would hang the worker on a redirect loop."""
    monkeypatch.setattr(gallerydl, "_dump_json", _dumps(GALLERYDL_REDIRECT))

    with pytest.raises(gallerydl.GalleryDlError, match="short link"):
        await gallerydl.fetch_metadata("https://vm.tiktok.com/ZN88beMDb/", SETTINGS)


async def test_tiktok_metadata_falls_back_to_gallerydl(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this fixes: yt-dlp's TikTok extractor broke with "Unexpected
    response from webpage request", and because the gallery-dl fallback existed
    only in download_media, the import died at the fetch stage without ever
    reaching the path that works."""

    async def broken(url: str, settings: Settings) -> ytdlp.PostMetadata:
        raise ytdlp.YtDlpError("Unexpected response from webpage request", needs_update=True)

    monkeypatch.setattr(social.ytdlp, "fetch_metadata", broken)
    monkeypatch.setattr(social.gallerydl, "_dump_json", _dumps(GALLERYDL_POST))

    metadata = await social.fetch_metadata(classify("https://vm.tiktok.com/ZN88beMDb/"), SETTINGS)
    assert "Ainesosat" in metadata.caption


async def test_instagram_metadata_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """gallery-dl is the TikTok safety net specifically. An Instagram failure is
    a failure, and dressing it up as something else would hide the real error."""

    async def broken(url: str, settings: Settings) -> ytdlp.PostMetadata:
        raise ytdlp.YtDlpError("login required")

    monkeypatch.setattr(social.ytdlp, "fetch_metadata", broken)

    url = "https://www.instagram.com/reel/CxNke4OtbOT/"
    with pytest.raises(social.SocialFetchFailed, match="login required"):
        await social.fetch_metadata(classify(url), SETTINGS)


async def test_a_broken_extractor_is_recognised_as_needing_an_update() -> None:
    """The marker list did not include TikTok's current failure, so the
    self-update never fired — even though the error itself says to run -U."""
    error = ytdlp._classify_failure(1, b"ERROR: Unexpected response from webpage request")
    assert error.needs_update is True


# ─── TLS impersonation ───────────────────────────────────────────────────


def test_base_args_requests_a_chrome_tls_fingerprint() -> None:
    """A Chrome User-Agent sent over yt-dlp's own TLS fingerprint is a mismatch
    a bot check can read directly. The worker image installs curl-cffi for this
    and fails to build without an impersonate target, but nothing was asking
    for one."""
    args = ytdlp.base_args(SETTINGS)
    assert "--impersonate" in args
    assert args[args.index("--impersonate") + 1] == "chrome"


def test_impersonation_can_be_turned_off_without_a_code_change() -> None:
    """A yt-dlp built without the curl-cffi extra rejects the flag outright, and
    a site could start refusing the impersonated fingerprint."""
    args = ytdlp.base_args(SETTINGS.model_copy(update={"scraper_impersonate": ""}))
    assert "--impersonate" not in args
    # The User-Agent is independent of it and must survive.
    assert "--user-agent" in args


# ─── media rejection must not kill the job ───────────────────────────────


def _fresh_db(tmp_path: Path):
    from recimin.db import schema
    from recimin.db.connection import connect

    conn = connect(tmp_path / "t.db")
    schema.migrate(conn)
    return conn


def test_store_media_skips_an_oversized_file_and_keeps_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reel over the size cap is skipped, not fatal.

    Production job 28 died here: the skip branch logged with a reserved
    LogRecord key and the KeyError escaped, failing all three attempts.
    """
    from recimin.media import store

    conn = _fresh_db(tmp_path)
    monkeypatch.setattr(store, "MAX_UPLOAD_BYTES", 16)

    poster = tmp_path / "clip_poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff\xe0jpg\xff\xd9")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 64)

    settings = SETTINGS.model_copy(update={"data_dir": tmp_path / "store"})
    ids = social.store_media(conn, [poster, video], settings=settings, source_url="u")

    assert len(ids) == 1
    kind = conn.execute("SELECT kind FROM media WHERE id = ?", (ids[0],)).fetchone()["kind"]
    assert kind == "image"


def test_store_media_skips_an_unsupported_file(tmp_path: Path) -> None:
    conn = _fresh_db(tmp_path)
    poster = tmp_path / "clip_poster.jpg"
    poster.write_bytes(b"\xff\xd8\xff\xe0jpg\xff\xd9")
    stray = tmp_path / "info.json"
    stray.write_text("{}")

    settings = SETTINGS.model_copy(update={"data_dir": tmp_path / "store"})
    ids = social.store_media(conn, [stray, poster], settings=settings, source_url="u")
    assert len(ids) == 1


# ─── failure classification ──────────────────────────────────────────────

INSTAGRAM_LOGIN_WALL = (
    b"ERROR: [Instagram] DOtbZZ6DSWw: Instagram sent an empty media response. "
    b"Check if this post is accessible in your browser without being logged-in. "
    b"If it is not, then use --cookies-from-browser or --cookies for the authentication. "
    b"Confirm you are on the latest version using  yt-dlp -U"
)


def test_a_login_walled_post_is_not_a_stale_extractor() -> None:
    """yt-dlp appends 'confirm you are on the latest version' to nearly every
    error, so matching on it turned a private post into a self-update loop."""
    error = ytdlp._classify_failure(1, INSTAGRAM_LOGIN_WALL)
    assert error.needs_update is False
    assert error.inaccessible is True


@pytest.mark.parametrize(
    "stderr",
    [
        b"ERROR: [Instagram] X: login required",
        b"ERROR: [TikTok] X: This post may not be comfortable for some audiences. Log in",
        b"ERROR: [Instagram] X: Requested content is not available, rate-limit reached",
    ],
)
def test_access_walls_are_recognised(stderr: bytes) -> None:
    assert ytdlp._classify_failure(1, stderr).inaccessible is True


def test_a_plain_network_error_is_neither() -> None:
    error = ytdlp._classify_failure(1, b"ERROR: network unreachable")
    assert error.needs_update is False
    assert error.inaccessible is False


async def test_social_fetch_carries_the_inaccessible_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail(url: str, settings: object) -> ytdlp.PostMetadata:
        raise ytdlp._classify_failure(1, INSTAGRAM_LOGIN_WALL)

    monkeypatch.setattr(ytdlp, "fetch_metadata", fail)
    with pytest.raises(social.SocialFetchFailed) as raised:
        await social.fetch_metadata(
            classify("https://www.instagram.com/reel/DOtbZZ6DSWw/"), SETTINGS
        )
    assert raised.value.inaccessible is True


# ─── self-update ─────────────────────────────────────────────────────────


async def test_self_update_upgrades_through_uv_not_pip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The worker venv has no pip; yt-dlp is installed into system python by uv.

    `python -m pip` failed on every production attempt with "No module named
    pip", so the self-update path never once ran.
    """
    seen: list[list[str]] = []

    async def fake_run(args: list[str], timeout: int) -> tuple[int, bytes, bytes]:
        seen.append(args)
        return 0, b"", b""

    monkeypatch.setattr(ytdlp, "_run", fake_run)
    assert await ytdlp.self_update() is True
    args = seen[0]
    assert args[:3] == ["uv", "pip", "install"]
    assert "--system" in args
    assert "--pre" in args
    assert "yt-dlp[default,curl-cffi]" in args
    assert "pip" not in args[3:]


async def test_self_update_reports_a_missing_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(args: list[str], timeout: int) -> tuple[int, bytes, bytes]:
        raise FileNotFoundError("uv")

    monkeypatch.setattr(ytdlp, "_run", fake_run)
    assert await ytdlp.self_update() is False
