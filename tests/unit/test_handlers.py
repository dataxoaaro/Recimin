"""Import orchestration.

The layer that decides what runs, in what order, and what happens when a piece
of it fails. Extractors are mocked; what is under test is the wiring.
"""

import sqlite3
from pathlib import Path

import pytest

from recimin.config import Settings
from recimin.db.models import CaptionGate, JobStatus, RecipeStatus
from recimin.db.repositories import ingredients as ing_repo
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import media as media_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories import tags as tags_repo
from recimin.db.repositories.recipes import RecipeDraft
from recimin.importer import social, web
from recimin.importer.normalise import NormalisedRecipe
from recimin.importer.urls import classify
from recimin.importer.ytdlp import PostMetadata
from recimin.llm import extract as llm_extract
from recimin.llm.schema import ExtractedRecipe
from recimin.worker import handlers
from recimin.worker.loop import NonRetryable

WEB_URL = "https://www.kinuskikissa.fi/perinteinen-mansikkakakku"
IG_URL = "https://www.instagram.com/p/DWjfQTDNm_l/"

RECIPE = NormalisedRecipe(
    title="Perinteinen mansikkakakku",
    ingredients=["5 munan sokerikakkupohja TAI", "5 munan gluteeniton kakkupohja", "2 dl kermaa"],
    instructions_md="1. Bake\n2. Assemble",
    servings=15,
    total_time_minutes=180,
    language="fi",
    author="Kinuskikissa",
)

METADATA = PostMetadata(
    post_id="DWjfQTDNm_l",
    caption="Kinderin valkoinen sisus ja maitosuklaakuori. Nam!\n\n#kinder #kakku",
    uploader="kinuskikissa",
    webpage_url=IG_URL,
)


def _job(conn: sqlite3.Connection, url: str) -> object:
    jobs_repo.enqueue(conn, input_url=url)
    return jobs_repo.claim_next(conn)


# ─── the web path ────────────────────────────────────────────────────────


async def test_web_import_is_published_not_flagged(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """schema.org is the site's own structured data, read deterministically.

    Everything used to land as a draft awaiting a review screen that was never
    built, so the badge appeared on every recipe and meant nothing. A parse that
    inferred nothing has nothing to review.
    """
    monkeypatch.setattr(web, "extract", lambda url, s: RECIPE)
    job = _job(db, WEB_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.status is RecipeStatus.PUBLISHED
    assert recipe.title == "Perinteinen mansikkakakku"
    assert recipe.source_site == "kinuskikissa.fi"
    assert recipe.source_author == "Kinuskikissa"
    assert recipe.imported_at is not None


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (None, RecipeStatus.PUBLISHED),  # schema.org, deterministic
        ("high", RecipeStatus.PUBLISHED),
        ("medium", RecipeStatus.DRAFT),
        ("low", RecipeStatus.DRAFT),
    ],
)
def test_only_an_uncertain_extraction_is_flagged(
    confidence: str | None, expected: RecipeStatus
) -> None:
    assert handlers.status_for(confidence) is expected


def test_an_unrecognised_confidence_is_treated_as_uncertain() -> None:
    """The value reaches us from a model. Anything unexpected should ask for a
    human rather than quietly claim the recipe is fine."""
    assert handlers.status_for("banana") is RecipeStatus.DRAFT
    assert handlers.status_for("") is RecipeStatus.DRAFT


async def test_web_import_parses_ingredients_deterministically(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web, "extract", lambda url, s: RECIPE)
    job = _job(db, WEB_URL)
    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    lines = ing_repo.for_recipe(db, recipe_id)  # type: ignore[arg-type]
    assert [line.raw_text for line in lines] == RECIPE.ingredients
    assert lines[2].qty == 2.0
    assert lines[2].unit == "dl"
    # "TAI" on line 0 makes line 1 an alternative, not a second purchase.
    assert lines[1].alternative_of == 0


async def test_a_web_recipe_gets_its_hero_image_downloaded(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """schema.org names the photo; without downloading it a web import renders
    as an empty card while a social import gets a poster."""
    with_image = NormalisedRecipe(
        title=RECIPE.title,
        ingredients=list(RECIPE.ingredients),
        instructions_md=RECIPE.instructions_md,
        image_url="https://www.kinuskikissa.fi/kakku.jpg",
    )
    monkeypatch.setattr(web, "extract", lambda url, s: with_image)
    monkeypatch.setattr(web, "download_image", lambda url, s: (b"fake-jpeg-bytes", "image/jpeg"))
    job = _job(db, WEB_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.hero_media_id is not None
    hero = media_repo.get(db, recipe.hero_media_id)
    assert hero is not None
    assert hero.recipe_id == recipe_id
    assert hero.source_url == "https://www.kinuskikissa.fi/kakku.jpg"
    assert (settings.data_dir / hero.file_path).is_file()


async def test_a_failed_hero_download_never_fails_the_import(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_image = NormalisedRecipe(
        title=RECIPE.title,
        ingredients=list(RECIPE.ingredients),
        instructions_md=RECIPE.instructions_md,
        image_url="https://www.kinuskikissa.fi/kakku.jpg",
    )
    monkeypatch.setattr(web, "extract", lambda url, s: with_image)
    monkeypatch.setattr(web, "download_image", lambda url, s: None)
    job = _job(db, WEB_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.hero_media_id is None


async def test_a_page_with_no_recipe_needs_attention_not_a_retry(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_recipe(url: str, s: Settings) -> NormalisedRecipe:
        raise web.NoRecipeFound("No recipe found on this page.")

    monkeypatch.setattr(web, "extract", no_recipe)
    job = _job(db, "https://www.valio.fi/reseptihaku/x")

    with pytest.raises(NonRetryable, match="No recipe found"):
        await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]


async def test_a_profile_is_rejected_before_any_fetch(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enumeration is what gets a residential IP throttled."""
    called = False

    async def should_not_run(*args: object, **kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("network was touched")

    monkeypatch.setattr(social, "fetch_metadata", should_not_run)
    job = _job(db, "https://www.instagram.com/kinuskikissa/")

    with pytest.raises(NonRetryable, match="individual post"):
        await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]
    assert called is False


async def test_an_already_imported_url_returns_the_existing_recipe(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = recipes_repo.create(
        db, RecipeDraft(title="Already here", source_url_normalised=classify(WEB_URL).normalised)
    )

    def should_not_run(url: str, s: Settings) -> NormalisedRecipe:
        raise AssertionError("re-fetched an already imported URL")

    monkeypatch.setattr(web, "extract", should_not_run)
    job = _job(db, WEB_URL)

    assert await handlers.handle_import(db, job, settings) == existing  # type: ignore[arg-type]


# ─── the photo path ──────────────────────────────────────────────────────

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _photo_job(db: sqlite3.Connection, settings: Settings) -> object:
    from recimin.db.models import MediaKind
    from recimin.media import store as media_store

    stored = media_store.store_bytes(PNG, "image/png", media_dir=settings.data_dir)
    media_id = media_repo.create(
        db,
        kind=MediaKind.IMAGE,
        file_path=stored.relative_path,
        sha256=stored.sha256,
        bytes_=stored.bytes,
        mime=stored.mime,
    )
    jobs_repo.enqueue(db, input_url="photos", kind="image", media_ids=[media_id])
    return jobs_repo.claim_next(db)


async def test_photos_become_a_recipe_with_the_uploads_as_media(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: dict[str, object] = {}

    async def fake_extract(images: list, s: Settings) -> ExtractedRecipe:
        received["images"] = images
        return ExtractedRecipe(
            title="Mummon lettutaikina",
            language="fi",
            category="sweet_baking",
            ingredients=[{"raw_text": "2 dl vehnäjauhoja"}],  # type: ignore[list-item]
            instructions_md="1. Sekoita",
            confidence="high",
        )

    monkeypatch.setattr(llm_extract, "from_photos", fake_extract)
    enabled = settings.model_copy(update={"llm_enabled": True, "openrouter_api_key": "k"})
    job = _photo_job(db, settings)

    recipe_id = await handlers.handle_import(db, job, enabled)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.title == "Mummon lettutaikina"
    assert recipe.category == "sweet_baking"
    assert str(recipe.source_platform) == "manual"
    assert recipe.source_url is None
    assert recipe.hero_media_id is not None
    hero = media_repo.get(db, recipe.hero_media_id)
    assert hero is not None and hero.recipe_id == recipe_id
    # The model was handed the actual stored file.
    assert [p.name for p in received["images"]] == [hero.file_path.rsplit("/", 1)[-1]]  # type: ignore[union-attr]


async def test_photo_import_without_the_llm_needs_attention(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The photo path has no fallback — no caption, no structured data — so a
    missing key must say so instead of silently doing nothing."""

    async def should_not_run(images: list, s: Settings) -> ExtractedRecipe:
        raise AssertionError("called the LLM without a key")

    monkeypatch.setattr(llm_extract, "from_photos", should_not_run)
    job = _photo_job(db, settings)  # settings has no api key

    with pytest.raises(NonRetryable, match="OPENROUTER_API_KEY"):
        await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]


async def test_photos_with_no_recipe_need_attention_not_a_retry(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuses(images: list, s: Settings) -> ExtractedRecipe:
        raise llm_extract.LlmRefused("schema validation failed twice")

    monkeypatch.setattr(llm_extract, "from_photos", refuses)
    enabled = settings.model_copy(update={"llm_enabled": True, "openrouter_api_key": "k"})
    job = _photo_job(db, settings)

    with pytest.raises(NonRetryable, match="No recipe could be read"):
        await handlers.handle_import(db, job, enabled)  # type: ignore[arg-type]


# ─── short links ─────────────────────────────────────────────────────────

TT_SHORT_URL = "https://vm.tiktok.com/ZM8abcDEF/"
TT_CANONICAL = "https://www.tiktok.com/@cook/video/7301234567890"


def _tiktok_metadata(webpage_url: str) -> PostMetadata:
    return PostMetadata(
        post_id="7301234567890",
        caption="Nopea arkiruoka",
        uploader="cook",
        webpage_url=webpage_url,
    )


async def test_a_short_link_to_an_imported_post_returns_the_existing_recipe(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route cannot dedupe a short link — only the worker learns the real
    target. Importing the same post twice must not download it twice, and must
    not crash on the unique source index."""
    existing = recipes_repo.create(
        db,
        RecipeDraft(title="Already here", source_url_normalised=classify(TT_CANONICAL).normalised),
    )

    async def fake_metadata(classified: object, s: Settings) -> PostMetadata:
        return _tiktok_metadata(TT_CANONICAL)

    async def should_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("downloaded media for a duplicate")

    monkeypatch.setattr(social, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(social, "download_media", should_not_run)
    job = _job(db, TT_SHORT_URL)

    assert await handlers.handle_import(db, job, settings) == existing  # type: ignore[arg-type]

    stored = jobs_repo.get(db, job.id)  # type: ignore[attr-defined]
    assert stored is not None
    assert stored.normalised_url == classify(TT_CANONICAL).normalised
    assert stored.platform == "tiktok"


async def test_a_new_short_link_persists_under_its_canonical_url(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-video-bytes")

    async def fake_metadata(classified: object, s: Settings) -> PostMetadata:
        return _tiktok_metadata(TT_CANONICAL)

    async def fake_download(classified: object, s: Settings) -> tuple[list[Path], str]:
        return [video], ""

    async def no_cleanup(paths: list[Path]) -> None:
        return None

    monkeypatch.setattr(social, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(social, "download_media", fake_download)
    monkeypatch.setattr(social, "cleanup", no_cleanup)
    job = _job(db, TT_SHORT_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.source_url_normalised == classify(TT_CANONICAL).normalised
    assert recipe.source_url == TT_SHORT_URL


# ─── the social path ─────────────────────────────────────────────────────


def _mock_social(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    caption: str = METADATA.caption,
    subtitles: str = "",
) -> Path:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42fake-video-bytes")

    async def fake_metadata(classified: object, s: Settings) -> PostMetadata:
        return PostMetadata(
            post_id=METADATA.post_id,
            caption=caption,
            uploader=METADATA.uploader,
            webpage_url=METADATA.webpage_url,
        )

    async def fake_download(classified: object, s: Settings) -> tuple[list[Path], str]:
        return [video], subtitles

    async def no_cleanup(paths: list[Path]) -> None:
        return None

    monkeypatch.setattr(social, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(social, "download_media", fake_download)
    monkeypatch.setattr(social, "cleanup", no_cleanup)
    return video


async def test_social_import_records_the_caption_gate(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Kinder caption has no ingredients, so the gate must miss."""
    _mock_social(monkeypatch, tmp_path)
    job = _job(db, IG_URL)

    await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    stored = jobs_repo.get(db, job.id)  # type: ignore[attr-defined]
    assert stored is not None
    assert stored.caption_gate is CaptionGate.MISS


async def test_a_caption_with_quantities_hits_the_gate(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_social(
        monkeypatch,
        tmp_path,
        caption="Mansikkakakku\n2 dl kermaa\n200 g mansikoita\n1 rkl sokeria",
    )
    job = _job(db, IG_URL)

    await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    stored = jobs_repo.get(db, job.id)  # type: ignore[attr-defined]
    assert stored is not None
    assert stored.caption_gate is CaptionGate.HIT


async def test_media_is_stored_and_becomes_the_hero(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Media is kept regardless of the gate: the source post may be deleted."""
    _mock_social(monkeypatch, tmp_path)
    job = _job(db, IG_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.hero_media_id is not None


async def test_the_transcript_is_kept_in_the_draft(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_social(monkeypatch, tmp_path, subtitles="Vatkaa kerma vaahdoksi.")
    job = _job(db, IG_URL)
    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert "Vatkaa kerma" in recipe.instructions_md


# ─── the LLM layer ───────────────────────────────────────────────────────


async def test_llm_output_replaces_the_caption_draft(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_social(monkeypatch, tmp_path)

    async def fake_extract(**kwargs: object) -> ExtractedRecipe:
        return ExtractedRecipe(
            title="Kinder-juustokakku",
            language="fi",
            category="cake",
            servings=12,
            ingredients=[
                {"raw_text": "200 g Kinder-suklaata"},  # type: ignore[list-item]
                {"raw_text": "2 dl kermaa"},  # type: ignore[list-item]
            ],
            instructions_md="1. Sulata suklaa",
            confidence="high",
        )

    monkeypatch.setattr(llm_extract, "from_social", fake_extract)
    enabled = settings.model_copy(update={"llm_enabled": True, "openrouter_api_key": "k"})
    job = _job(db, IG_URL)

    recipe_id = await handlers.handle_import(db, job, enabled)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.title == "Kinder-juustokakku"
    lines = ing_repo.for_recipe(db, recipe_id)  # type: ignore[arg-type]
    assert [line.raw_text for line in lines] == ["200 g Kinder-suklaata", "2 dl kermaa"]
    assert lines[0].qty == 200.0


async def test_the_llm_category_and_tags_are_persisted(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The schema demands a category and offers a tag vocabulary; storing the
    answer is the whole point of asking. An invented tag is dropped rather than
    let into the vocabulary."""
    _mock_social(monkeypatch, tmp_path)

    async def fake_extract(**kwargs: object) -> ExtractedRecipe:
        return ExtractedRecipe(
            title="Kinder-juustokakku",
            language="fi",
            category="cake",
            tags=["Party", "make-ahead", "kinder-viral"],
            ingredients=[{"raw_text": "200 g Kinder-suklaata"}],  # type: ignore[list-item]
            instructions_md="1. Sulata suklaa",
            confidence="high",
        )

    monkeypatch.setattr(llm_extract, "from_social", fake_extract)
    enabled = settings.model_copy(update={"llm_enabled": True, "openrouter_api_key": "k"})
    job = _job(db, IG_URL)

    recipe_id = await handlers.handle_import(db, job, enabled)  # type: ignore[arg-type]

    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.category == "cake"
    assert tags_repo.for_recipe(db, recipe_id) == ["make-ahead", "party"]  # type: ignore[arg-type]


async def test_a_schema_org_category_lands_on_the_vocabulary(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """recipeCategory is a human-facing string like "Dessert"; it must resolve
    to a key rather than default everything to dinner."""
    recipe = NormalisedRecipe(
        title="Mustikkapiirakka",
        ingredients=["2 dl kermaa"],
        instructions_md="1. Bake",
        category="Dessert",
    )
    monkeypatch.setattr(web, "extract", lambda url, s: recipe)
    job = _job(db, WEB_URL)

    recipe_id = await handlers.handle_import(db, job, settings)  # type: ignore[arg-type]

    stored = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert stored is not None
    assert stored.category == "sweet_baking"


async def test_a_failing_llm_still_yields_a_usable_draft(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The media is archived and the caption preserved. Better than nothing."""
    _mock_social(monkeypatch, tmp_path)

    async def broken(**kwargs: object) -> ExtractedRecipe:
        raise llm_extract.LlmUnavailable("OpenRouter credit exhausted")

    monkeypatch.setattr(llm_extract, "from_social", broken)
    enabled = settings.model_copy(update={"llm_enabled": True, "openrouter_api_key": "k"})
    job = _job(db, IG_URL)

    recipe_id = await handlers.handle_import(db, job, enabled)  # type: ignore[arg-type]

    stored = jobs_repo.get(db, job.id)  # type: ignore[attr-defined]
    assert stored is not None
    assert stored.status is JobStatus.RUNNING  # finish() is the loop's job
    recipe = recipes_repo.get(db, recipe_id)  # type: ignore[arg-type]
    assert recipe is not None
    assert recipe.hero_media_id is not None
    assert "Kinderin valkoinen" in recipe.instructions_md


async def test_the_llm_is_never_called_when_disabled(
    db: sqlite3.Connection, settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _mock_social(monkeypatch, tmp_path)

    async def should_not_run(**kwargs: object) -> ExtractedRecipe:
        raise AssertionError("called the LLM while disabled")

    monkeypatch.setattr(llm_extract, "from_social", should_not_run)
    job = _job(db, IG_URL)

    # settings has no API key, so extraction must be skipped silently.
    assert await handlers.handle_import(db, job, settings) is not None  # type: ignore[arg-type]
