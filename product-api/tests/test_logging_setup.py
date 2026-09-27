import json
import logging
import sys

from app.logging_setup import JsonFormatter


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord("product_api", logging.WARNING, __file__, 1, "slow request", (), None)
    record.__dict__.update(extra)
    return record


def test_log_line_is_json_with_service_and_extras():
    line = JsonFormatter("product-api").format(_record(duration_ms=812.5))

    payload = json.loads(line)
    assert (payload["service"], payload["level"], payload["msg"], payload["duration_ms"]) == (
        "product-api",
        "WARNING",
        "slow request",
        812.5,
    )


def test_exceptions_are_included():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())

    assert "ValueError: boom" in json.loads(JsonFormatter("svc").format(record))["exc"]
