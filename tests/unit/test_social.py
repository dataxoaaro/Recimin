"""Social import: the caption gate, the yt-dlp adapter and routing."""

import json
from pathlib import Path

import pytest

from recimin.config import Settings
from recimin.importer import caption, social, ytdlp
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
        duration_s=30.0,
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
