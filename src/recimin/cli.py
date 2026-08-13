"""Command line entry point.

Subcommands are added as phases land: `db migrate` in Phase 1, `user create` in Phase 2.
"""

import argparse
import sys

from recimin import __version__
from recimin.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(prog="recimin", description="Recimin admin commands")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_subparsers(dest="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1
    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
