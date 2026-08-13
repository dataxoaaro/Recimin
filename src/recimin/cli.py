"""Command line entry point.

Migrations are deliberately manual. Deploy ships code only; a schema change must
be applied before the new code starts.
"""

import argparse
import sys

from recimin import __version__
from recimin.config import get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.logging import configure_logging


def _db_migrate(_: argparse.Namespace) -> int:
    settings = get_settings()
    conn = connect(settings.db_path)
    version = schema.migrate(conn)
    print(f"schema version {version}")
    return 0


def _db_version(_: argparse.Namespace) -> int:
    settings = get_settings()
    conn = connect(settings.db_path)
    print(schema.current_version(conn))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(prog="recimin", description="Recimin admin commands")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    db = sub.add_parser("db", help="database maintenance").add_subparsers(dest="db_command")
    db.add_parser("migrate", help="apply pending migrations").set_defaults(func=_db_migrate)
    db.add_parser("version", help="print the current schema version").set_defaults(func=_db_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
