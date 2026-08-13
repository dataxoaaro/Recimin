"""Migration runner and the initial schema.

The constraints asserted here are the ones that silently corrupt data if they
regress, not merely the ones that would crash.
"""

import sqlite3
from pathlib import Path

import pytest

from recimin.db import schema
from recimin.db.connection import connect

# ─── the runner ──────────────────────────────────────────────────────────


def test_discover_orders_by_version(tmp_path: Path) -> None:
    for name in ("0002_second.sql", "0001_first.sql", "0003_third.sql"):
        (tmp_path / name).write_text("SELECT 1;")
    assert [v for v, _ in schema.discover(tmp_path)] == [1, 2, 3]


def test_discover_rejects_bad_filename(tmp_path: Path) -> None:
    (tmp_path / "initial.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match=r"NNNN_name\.sql"):
        schema.discover(tmp_path)


def test_discover_rejects_version_gap(tmp_path: Path) -> None:
    """A gap almost always means a file was renamed or lost."""
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0003_c.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="contiguous"):
        schema.discover(tmp_path)


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    assert schema.migrate(conn) == 1
    assert schema.migrate(conn) == 1
    assert schema.current_version(conn) == 1


def test_failed_migration_rolls_back_whole_file(tmp_path: Path) -> None:
    """A migration lands whole or not at all, and the version does not advance."""
    migrations = tmp_path / "m"
    migrations.mkdir()
    (migrations / "0001_broken.sql").write_text(
        "CREATE TABLE good (id INTEGER);\nTHIS IS NOT SQL;\n"
    )
    conn = connect(tmp_path / "t.db")

    with pytest.raises(sqlite3.Error):
        schema.migrate(conn, migrations)

    assert schema.current_version(conn) == 0
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "good" not in tables


# ─── the initial schema ──────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "recimin.db")
    schema.migrate(conn)
    return conn


def _recipe(conn: sqlite3.Connection, title: str = "Test", **kw: object) -> int:
    cols = {
        "title": title,
        "created_at": "2026-08-13T00:00:00Z",
        "updated_at": "2026-08-13T00:00:00Z",
        **kw,
    }
    names = ", ".join(cols)
    holes = ", ".join("?" * len(cols))
    cur = conn.execute(f"INSERT INTO recipes ({names}) VALUES ({holes})", tuple(cols.values()))
    return int(cur.lastrowid or 0)


def test_all_tables_exist(db: sqlite3.Connection) -> None:
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "users",
        "api_tokens",
        "media",
        "recipes",
        "ingredients",
        "tags",
        "recipe_tags",
        "jobs",
        "push_subscriptions",
        "recipes_fts",
    } <= names


def test_source_url_unique_but_nulls_are_free(db: sqlite3.Connection) -> None:
    """The dedupe mechanism. Many manual recipes have no source at all."""
    _recipe(db, "a", source_url_normalised="https://x.fi/r")
    with pytest.raises(sqlite3.IntegrityError):
        _recipe(db, "b", source_url_normalised="https://x.fi/r")

    _recipe(db, "c")
    _recipe(db, "d")
    assert (
        db.execute("SELECT count(*) FROM recipes WHERE source_url_normalised IS NULL").fetchone()[0]
        == 2
    )


def test_foreign_keys_are_enforced(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (9999, 0, 'x')")


def test_delete_cascades_to_children(db: sqlite3.Connection) -> None:
    rid = _recipe(db)
    db.execute(
        "INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, '2 dl kermaa')",
        (rid,),
    )
    db.execute("INSERT INTO tags (name) VALUES ('quick')")
    db.execute("INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, 1)", (rid,))
    db.execute(
        "INSERT INTO media (recipe_id, kind, file_path, sha256, bytes, mime, created_at)"
        " VALUES (?, 'image', 'media/aa/aa.jpg', 'aa', 1, 'image/jpeg', '2026-08-13')",
        (rid,),
    )

    db.execute("DELETE FROM recipes WHERE id = ?", (rid,))

    for table in ("ingredients", "recipe_tags", "media"):
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    # The tag itself survives; only the association goes.
    assert db.execute("SELECT count(*) FROM tags").fetchone()[0] == 1


def test_status_and_category_checks(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _recipe(db, status="nonsense")
    with pytest.raises(sqlite3.IntegrityError):
        _recipe(db, source_platform="myspace")


def test_ingredient_position_is_unique_per_recipe(db: sqlite3.Connection) -> None:
    rid = _recipe(db)
    db.execute("INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, 'a')", (rid,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, 'b')", (rid,)
        )


def test_job_status_check(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO jobs (status, input_url, created_at) VALUES ('maybe', 'u', 'now')")


def test_caption_gate_check(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO jobs (status, input_url, created_at, caption_gate)"
        " VALUES ('done', 'u', 'now', 'hit')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO jobs (status, input_url, created_at, caption_gate)"
            " VALUES ('done', 'u', 'now', 'maybe')"
        )


# ─── full text search ────────────────────────────────────────────────────


def _fts(db: sqlite3.Connection, query: str) -> list[int]:
    return [
        r[0]
        for r in db.execute("SELECT rowid FROM recipes_fts WHERE recipes_fts MATCH ?", (query,))
    ]


def test_fts_indexes_title_on_insert(db: sqlite3.Connection) -> None:
    rid = _recipe(db, "Mansikkakakku")
    assert _fts(db, "mansikkakakku") == [rid]


def test_fts_finds_by_ingredient_not_in_the_title(db: sqlite3.Connection) -> None:
    rid = _recipe(db, "Sunday bake")
    db.execute(
        "INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, '2 dl kermaviiliä')",
        (rid,),
    )
    assert _fts(db, "kermaviilia") == [rid]


def test_fts_finds_by_tag(db: sqlite3.Connection) -> None:
    rid = _recipe(db)
    db.execute("INSERT INTO tags (name) VALUES ('weeknight')")
    db.execute("INSERT INTO recipe_tags (recipe_id, tag_id) VALUES (?, 1)", (rid,))
    assert _fts(db, "weeknight") == [rid]


def test_fts_ignores_finnish_diacritics(db: sqlite3.Connection) -> None:
    """remove_diacritics 2 means a phone keyboard without umlauts still finds it."""
    rid = _recipe(db, "Porkkanalaatikko ja lohtä")
    assert _fts(db, "lohta") == [rid]
    assert _fts(db, "lohtä") == [rid]


def test_fts_follows_title_updates(db: sqlite3.Connection) -> None:
    rid = _recipe(db, "Old name")
    db.execute("UPDATE recipes SET title = 'Brand new name' WHERE id = ?", (rid,))
    assert _fts(db, "old") == []
    assert _fts(db, "brand") == [rid]


def test_fts_row_disappears_with_the_recipe(db: sqlite3.Connection) -> None:
    rid = _recipe(db, "Ephemeral")
    db.execute("INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, 'x')", (rid,))
    db.execute("DELETE FROM recipes WHERE id = ?", (rid,))
    assert db.execute("SELECT count(*) FROM recipes_fts").fetchone()[0] == 0


def test_fts_reflects_removed_ingredients(db: sqlite3.Connection) -> None:
    rid = _recipe(db)
    db.execute(
        "INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, 0, 'saffron')", (rid,)
    )
    assert _fts(db, "saffron") == [rid]
    db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (rid,))
    assert _fts(db, "saffron") == []


def test_fts_has_exactly_one_row_per_recipe(db: sqlite3.Connection) -> None:
    """The triggers delete-then-insert; a bug there would duplicate rows."""
    rid = _recipe(db, "Cake")
    for i, text in enumerate(["a", "b", "c"]):
        db.execute(
            "INSERT INTO ingredients (recipe_id, position, raw_text) VALUES (?, ?, ?)",
            (rid, i, text),
        )
    db.execute("UPDATE recipes SET title = 'Cake II' WHERE id = ?", (rid,))
    assert db.execute("SELECT count(*) FROM recipes_fts").fetchone()[0] == 1


def test_a_missing_migrations_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        schema.discover(tmp_path / "nope")


def test_an_empty_migrations_directory_raises(tmp_path: Path) -> None:
    """'Up to date at version 0' is a lie.

    It hides a container built without the migrations directory: the app starts,
    reports healthy, and 500s on the first request that touches a table.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no migrations"):
        schema.discover(empty)
