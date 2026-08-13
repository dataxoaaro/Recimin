"""CLI wiring."""

import pytest

from recimin.cli import build_parser, main


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0


def test_no_command_prints_help_and_fails() -> None:
    assert main([]) == 1
