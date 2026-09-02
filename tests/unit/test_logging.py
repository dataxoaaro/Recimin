"""Logs must be single-line JSON with no decoration."""

import json
import logging

from recimin.logging import JsonFormatter


def test_formats_as_json() -> None:
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "hello", (), None)
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["msg"] == "hello"
    assert parsed["level"] == "info"
    assert parsed["logger"] == "t"


def test_includes_extra_fields() -> None:
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "job", (), None)
    record.job_id = 7
    record.stage = "fetch"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["job_id"] == 7
    assert parsed["stage"] == "fetch"


def test_output_is_a_single_line() -> None:
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "multi\nline", (), None)
    assert "\n" not in JsonFormatter().format(record)


def test_no_log_call_uses_a_reserved_logrecord_key() -> None:
    """`extra={"name": ...}` raises KeyError inside logging.makeRecord, so the
    log line never prints and the exception replaces whatever was being
    handled. A production import died this way; catch the next one here."""
    import ast
    from pathlib import Path

    from recimin.logging import _RESERVED

    offenders: list[str] = []
    for path in sorted(Path("src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                    continue
                for key in keyword.value.keys:
                    if isinstance(key, ast.Constant) and key.value in _RESERVED:
                        offenders.append(f"{path}:{node.lineno} extra key {key.value!r}")
    assert offenders == []
