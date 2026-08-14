"""Command line entry point.

Migrations are deliberately manual. Deploy ships code only; a schema change must
be applied before the new code starts.
"""

import argparse
import sys
from getpass import getpass

from recimin import __version__
from recimin.api import auth
from recimin.config import get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.db.repositories import users as users_repo
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


def _user_create(args: argparse.Namespace) -> int:
    """Create an account from the command line.

    The only user-management surface there is. Recimin deliberately has no admin
    HTTP routes: that is where Arboretium grew a privilege-escalation bug.
    """
    password = args.password or getpass("Password: ")
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        print(f"password must be at least {auth.MIN_PASSWORD_LENGTH} characters")
        return 1

    settings = get_settings()
    conn = connect(settings.db_path)
    if users_repo.get_by_email(conn, args.email) is not None:
        print("that email is already registered")
        return 1

    user_id = users_repo.create(
        conn,
        email=args.email,
        password_hash=auth.hash_password(password),
        display_name=args.name or args.email.split("@")[0],
    )
    print(f"created user {user_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(prog="recimin", description="Recimin admin commands")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    db = sub.add_parser("db", help="database maintenance").add_subparsers(dest="db_command")
    db.add_parser("migrate", help="apply pending migrations").set_defaults(func=_db_migrate)
    db.add_parser("version", help="print the current schema version").set_defaults(func=_db_version)

    user = sub.add_parser("user", help="account management").add_subparsers(dest="user_command")
    create = user.add_parser("create", help="create an account")
    create.add_argument("email")
    create.add_argument("--name", default=None, help="display name")
    create.add_argument("--password", default=None, help="omit to be prompted")
    create.set_defaults(func=_user_create)

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
