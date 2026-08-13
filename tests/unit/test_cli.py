"""CLI wiring."""

import pytest

from recimin.cli import build_parser, main


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0


def test_no_command_prints_help_and_fails() -> None:
    assert main([]) == 1


def test_user_create_from_the_command_line(tmp_path, monkeypatch) -> None:
    """The only user-management surface. There are deliberately no admin routes."""
    import sqlite3

    from recimin.config import Settings, get_settings
    from recimin.db import schema
    from recimin.db.connection import connect

    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("SITE_PASSWORD", "site-password")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    schema.migrate(connect(tmp_path / "recimin.db"))

    assert main(["user", "create", "a@b.fi", "--password", "long-enough-pass"]) == 0
    # Second time round the email is taken.
    assert main(["user", "create", "a@b.fi", "--password", "long-enough-pass"]) == 1
    # Weak passwords are refused before any write.
    assert main(["user", "create", "c@d.fi", "--password", "short"]) == 1

    conn: sqlite3.Connection = connect(tmp_path / "recimin.db")
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    get_settings.cache_clear()
