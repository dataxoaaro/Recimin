"""Repository behaviour."""

import sqlite3
from pathlib import Path

import pytest

from recimin.db import schema
from recimin.db.connection import connect
from recimin.db.models import CaptionGate, JobStage, JobStatus, MediaKind, RecipeStatus
from recimin.db.repositories import ingredients as ing_repo
from recimin.db.repositories import jobs as jobs_repo
from recimin.db.repositories import media as media_repo
from recimin.db.repositories import recipes as recipes_repo
from recimin.db.repositories import tags as tags_repo
from recimin.db.repositories import users as users_repo
from recimin.db.repositories.ingredients import IngredientDraft
from recimin.db.repositories.recipes import RecipeDraft


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "recimin.db")
    schema.migrate(conn)
    return conn


# ─── recipes ─────────────────────────────────────────────────────────────


def test_create_writes_recipe_ingredients_and_tags_together(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(
        db,
        RecipeDraft(title="Mansikkakakku", instructions_md="1. Bake\n2. Wait", category="cake"),
        ingredient_lines=[
            IngredientDraft(raw_text="5 munan sokerikakkupohja TAI"),
            IngredientDraft(raw_text="5 munan gluteeniton kakkupohja", alternative_of=0),
            IngredientDraft(raw_text="2 dl kermaa", qty=2.0, unit="dl", item="kermaa"),
        ],
        tag_names=["Summer", "summer", "  Party  "],
    )

    recipe = recipes_repo.get(db, rid)
    assert recipe is not None
    assert recipe.title == "Mansikkakakku"
    assert recipe.status is RecipeStatus.DRAFT
    assert recipe.category == "cake"

    lines = ing_repo.for_recipe(db, rid)
    assert [line.position for line in lines] == [0, 1, 2]
    assert lines[1].alternative_of == 0
    assert lines[2].qty == 2.0

    # Duplicates and casing collapse to one canonical tag each.
    assert tags_repo.for_recipe(db, rid) == ["party", "summer"]


def test_create_rolls_back_entirely_on_a_bad_ingredient(db: sqlite3.Connection) -> None:
    """A half-saved recipe is worse than a failed save."""
    with pytest.raises(sqlite3.Error):
        recipes_repo.create(
            db,
            RecipeDraft(title="Doomed"),
            ingredient_lines=[IngredientDraft(raw_text=None)],  # type: ignore[arg-type]
        )
    assert recipes_repo.list_recipes(db) == []


def test_get_by_normalised_url(db: sqlite3.Connection) -> None:
    url = "https://www.kinuskikissa.fi/perinteinen-mansikkakakku"
    recipes_repo.create(db, RecipeDraft(title="Cake", source_url_normalised=url))
    assert recipes_repo.get_by_normalised_url(db, url) is not None
    assert recipes_repo.get_by_normalised_url(db, url + "/other") is None


def test_update_rejects_unknown_columns(db: sqlite3.Connection) -> None:
    """A typo must fail loudly rather than silently updating nothing."""
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    with pytest.raises(ValueError, match="unknown recipe columns"):
        recipes_repo.update(db, rid, titel="Y")


def test_update_coerces_enums_and_bools(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    recipes_repo.update(db, rid, status=RecipeStatus.PUBLISHED, is_favourite=True)
    recipe = recipes_repo.get(db, rid)
    assert recipe is not None
    assert recipe.status is RecipeStatus.PUBLISHED
    assert recipe.is_favourite is True


def test_replace_all_renumbers_positions(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(
        db,
        RecipeDraft(title="X"),
        ingredient_lines=[IngredientDraft(raw_text=f"line {i}") for i in range(4)],
    )
    ing_repo.replace_all(db, rid, [IngredientDraft(raw_text="only one")])
    lines = ing_repo.for_recipe(db, rid)
    assert len(lines) == 1
    assert lines[0].position == 0


def test_delete_returns_whether_a_row_went(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    assert recipes_repo.delete(db, rid) is True
    assert recipes_repo.delete(db, rid) is False


# ─── listing and search ──────────────────────────────────────────────────


def _seed(db: sqlite3.Connection) -> None:
    recipes_repo.create(
        db,
        RecipeDraft(title="Shanghai taco salad", category="salad"),
        ingredient_lines=[IngredientDraft(raw_text="1 lime")],
        tag_names=["quick"],
    )
    recipes_repo.create(
        db,
        RecipeDraft(title="Perinteinen mansikkakakku", category="cake", is_favourite=True),
        ingredient_lines=[IngredientDraft(raw_text="2 dl kermaa")],
        tag_names=["party"],
    )


def test_filters_compose(db: sqlite3.Connection) -> None:
    _seed(db)
    assert len(recipes_repo.list_recipes(db)) == 2
    assert len(recipes_repo.list_recipes(db, category="cake")) == 1
    assert len(recipes_repo.list_recipes(db, favourite=True)) == 1
    assert len(recipes_repo.list_recipes(db, tag="quick")) == 1
    assert len(recipes_repo.list_recipes(db, category="cake", favourite=True)) == 1
    assert len(recipes_repo.list_recipes(db, category="salad", favourite=True)) == 0


def test_text_query_matches_an_ingredient(db: sqlite3.Connection) -> None:
    _seed(db)
    found = recipes_repo.list_recipes(db, query="kermaa")
    assert [r.title for r in found] == ["Perinteinen mansikkakakku"]


def test_text_query_is_prefix_matched(db: sqlite3.Connection) -> None:
    """Typing part of a word on a phone keyboard should still find it."""
    _seed(db)
    assert len(recipes_repo.list_recipes(db, query="mansikka")) == 1


def test_search_box_punctuation_does_not_raise(db: sqlite3.Connection) -> None:
    """FTS5 MATCH has its own syntax; unescaped input would be a syntax error."""
    _seed(db)
    for nasty in ('"', "AND", "a OR b", "NEAR(", "*", "' OR 1=1 --", ""):
        assert recipes_repo.list_recipes(db, query=nasty) is not None


# ─── media ───────────────────────────────────────────────────────────────


def test_media_lifecycle(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    mid = media_repo.create(
        db,
        kind=MediaKind.IMAGE,
        file_path="media/ab/abcd.jpg",
        sha256="abcd",
        bytes_=1024,
        mime="image/jpeg",
        recipe_id=rid,
    )
    assert media_repo.total_bytes(db) == 1024
    assert media_repo.find_by_sha256(db, "abcd") is not None
    assert len(media_repo.for_recipe(db, rid)) == 1

    # Media rows go with their recipe; only the job history outlives it.
    recipes_repo.delete(db, rid)
    assert media_repo.get(db, mid) is None
    assert media_repo.total_bytes(db) == 0


# ─── users and tokens ────────────────────────────────────────────────────


def test_email_lookup_is_case_insensitive(db: sqlite3.Connection) -> None:
    users_repo.create(db, email="Aaro@Example.fi", password_hash="h", display_name="Aaro")
    assert users_repo.get_by_email(db, "aaro@example.fi") is not None
    assert users_repo.get_by_email(db, "AARO@EXAMPLE.FI") is not None


def test_duplicate_email_differing_only_in_case_is_rejected(db: sqlite3.Connection) -> None:
    users_repo.create(db, email="a@b.fi", password_hash="h", display_name="A")
    with pytest.raises(sqlite3.IntegrityError):
        users_repo.create(db, email="A@B.FI", password_hash="h", display_name="A")


def test_revoked_token_becomes_invisible(db: sqlite3.Connection) -> None:
    uid = users_repo.create(db, email="a@b.fi", password_hash="h", display_name="A")
    tid = users_repo.create_token(db, user_id=uid, name="iPhone", token_hash="deadbeef")

    assert users_repo.get_active_token(db, "deadbeef") is not None
    assert users_repo.revoke_token(db, tid) is True
    assert users_repo.get_active_token(db, "deadbeef") is None
    # Revoking twice is not an error but reports no change.
    assert users_repo.revoke_token(db, tid) is False
    # The row is still listed so the user can see the device was removed.
    assert len(users_repo.tokens_for_user(db, uid)) == 1


# ─── jobs ────────────────────────────────────────────────────────────────


def test_claim_takes_the_oldest_and_only_once(db: sqlite3.Connection) -> None:
    first = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.enqueue(db, input_url="https://b")

    claimed = jobs_repo.claim_next(db)
    assert claimed is not None
    assert claimed.id == first
    assert claimed.status is JobStatus.RUNNING
    assert claimed.attempts == 1

    # The first job is no longer claimable.
    second = jobs_repo.claim_next(db)
    assert second is not None
    assert second.id != first

    assert jobs_repo.claim_next(db) is None


def test_retryable_failure_requeues_then_fails(db: sqlite3.Connection) -> None:
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    for _ in range(jobs_repo.MAX_ATTEMPTS - 1):
        jobs_repo.claim_next(db)
        assert jobs_repo.fail(db, job_id, "timeout") is JobStatus.QUEUED

    jobs_repo.claim_next(db)
    assert jobs_repo.fail(db, job_id, "timeout") is JobStatus.FAILED

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.last_error == "timeout"
    assert job.finished_at is not None


def test_non_retryable_failure_needs_attention_immediately(db: sqlite3.Connection) -> None:
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.claim_next(db)
    status = jobs_repo.fail(db, job_id, "yt-dlp broke", retryable=False)
    assert status is JobStatus.NEEDS_ATTENTION


def test_release_does_not_burn_an_attempt(db: sqlite3.Connection) -> None:
    """Graceful shutdown must not push a job closer to permanent failure."""
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.claim_next(db)
    jobs_repo.release(db, job_id)

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.QUEUED
    assert job.attempts == 0


def test_reclaim_stale_recovers_from_a_crashed_worker(db: sqlite3.Connection) -> None:
    jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.claim_next(db)
    assert jobs_repo.reclaim_stale(db) == 1
    assert jobs_repo.queue_depth(db) == 1


def test_requeue_only_applies_to_terminal_failures(db: sqlite3.Connection) -> None:
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    assert jobs_repo.requeue(db, job_id) is False  # still queued

    jobs_repo.claim_next(db)
    jobs_repo.fail(db, job_id, "broke", retryable=False)
    assert jobs_repo.requeue(db, job_id) is True

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.attempts == 0
    assert job.last_error is None


def test_finish_records_the_recipe_and_clears_the_stage(db: sqlite3.Connection) -> None:
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.claim_next(db)
    jobs_repo.set_stage(db, job_id, JobStage.EXTRACT)
    jobs_repo.set_caption_gate(db, job_id, CaptionGate.MISS)
    jobs_repo.finish(db, job_id, recipe_id=rid)

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.status is JobStatus.DONE
    assert job.stage is None
    assert job.recipe_id == rid
    assert job.caption_gate is CaptionGate.MISS


def test_set_resolved_records_the_canonical_url(db: sqlite3.Connection) -> None:
    """A short link's job row starts with the opaque token; the worker replaces
    it with the real post as soon as yt-dlp reveals it."""
    job_id = jobs_repo.enqueue(
        db, input_url="https://vm.tiktok.com/ZM8abc/", normalised_url="https://vm.tiktok.com/ZM8abc"
    )
    jobs_repo.set_resolved(
        db, job_id, normalised_url="https://tiktok.com/@cook/video/123", platform="tiktok"
    )

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.normalised_url == "https://tiktok.com/@cook/video/123"
    assert job.platform == "tiktok"


def test_prune_removes_only_stale_terminal_jobs(db: sqlite3.Connection) -> None:
    """History older than the window goes; anything live or actionable stays."""
    ancient = "2020-01-01T00:00:00Z"

    done_old = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.finish(db, done_old)
    failed_old = jobs_repo.enqueue(db, input_url="https://b")
    db.execute("UPDATE jobs SET status = 'failed' WHERE id = ?", (failed_old,))
    attention_old = jobs_repo.enqueue(db, input_url="https://c")
    db.execute("UPDATE jobs SET status = 'needs_attention' WHERE id = ?", (attention_old,))
    for job_id in (done_old, failed_old, attention_old):
        db.execute("UPDATE jobs SET finished_at = ? WHERE id = ?", (ancient, job_id))

    done_recent = jobs_repo.enqueue(db, input_url="https://d")
    jobs_repo.finish(db, done_recent)
    queued = jobs_repo.enqueue(db, input_url="https://e")

    assert jobs_repo.prune_terminal(db) == 2

    remaining = {job.id for job in jobs_repo.recent(db)}
    assert remaining == {attention_old, done_recent, queued}


def test_deleting_a_recipe_leaves_its_job_row(db: sqlite3.Connection) -> None:
    """Import history must survive the recipe it produced."""
    rid = recipes_repo.create(db, RecipeDraft(title="X"))
    job_id = jobs_repo.enqueue(db, input_url="https://a")
    jobs_repo.finish(db, job_id, recipe_id=rid)
    recipes_repo.delete(db, rid)

    job = jobs_repo.get(db, job_id)
    assert job is not None
    assert job.recipe_id is None
