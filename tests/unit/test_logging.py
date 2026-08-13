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
