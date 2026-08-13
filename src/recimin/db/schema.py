"""Migration runner.

Numbered SQL files under migrations/, applied in order, tracked by
PRAGMA user_version. Each file runs inside one transaction: a migration either
lands whole or not at all.

Migrations are never applied automatically on deploy. Run `recimin db migrate`
before shipping a schema change.
"""

import contextlib
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
_FILENAME = re.compile(r"^(\d{4})_[\w-]+\.sql$")


def discover(migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Return (version, path) pairs sorted by version.

    Raises if numbering is duplicated or non-contiguous from 1 — a gap almost
    always means a file was renamed or lost, and applying around it corrupts the
    version counter.
    """
    if not migrations_dir.is_dir():
        raise FileNotFoundError(f"migrations directory not found: {migrations_dir}")

    found: list[tuple[int, Path]] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise ValueError(f"migration filename must be NNNN_name.sql: {path.name}")
        found.append((int(match.group(1)), path))

    if not found:
        # "up to date at version 0" is a lie that only surfaces on a cold start,
        # when the app comes up with no schema and every request 500s. This is
        # exactly how a Dockerfile that forgot to COPY migrations/ stayed hidden
        # behind a host-mounted database that already had one.
        raise FileNotFoundError(f"no migrations found in {migrations_dir}")

    versions = [v for v, _ in found]
    if len(set(versions)) != len(versions):
        raise ValueError(f"duplicate migration versions: {versions}")
    if versions and versions != list(range(1, len(versions) + 1)):
        raise ValueError(f"migration versions must be contiguous from 1: {versions}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version recorded in the database."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> int:
    """Apply every pending migration. Returns the resulting version.

    Idempotent: running it twice applies nothing the second time.
    """
    version = current_version(conn)
    applied = 0

    for target, path in discover(migrations_dir):
        if target <= version:
            continue
        sql = path.read_text(encoding="utf-8")
        # The BEGIN must live inside the script. sqlite3.executescript issues an
        # implicit COMMIT before it runs, so a transaction opened with a separate
        # conn.execute("BEGIN") would be closed before the first statement lands
        # and a mid-script failure would leave the schema half-applied.
        #
        # PRAGMA user_version cannot be parameterised, hence the f-string. The
        # value is an int parsed from the filename by discover(), never user input.
        script = f"BEGIN;\n{sql}\nPRAGMA user_version = {target};\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception:
            # conn.execute, not executescript: executescript would issue its own
            # implicit COMMIT first and permanently land the half-applied schema.
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            logger.exception("migration failed", extra={"version": target, "file": path.name})
            raise
        version = target
        applied += 1
        logger.info("migration applied", extra={"version": target, "file": path.name})

    if applied == 0:
        logger.info("schema up to date", extra={"version": version})
    return version
