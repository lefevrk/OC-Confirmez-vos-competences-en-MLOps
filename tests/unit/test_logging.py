"""Unit tests for the structured JSON log format used by the API."""

import json
import logging

from loguru import logger

from api.infra.logging import configure_logging


def test_configure_logging_emits_one_json_line_with_bound_fields(capsys) -> None:
    """A bound log call produces one JSON line with its extra fields included."""
    configure_logging()

    logger.bind(request_id="abc-123", latency_ms=4.2).info("prediction served")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["level"] == "INFO"
    assert record["message"] == "prediction served"
    assert record["request_id"] == "abc-123"
    assert record["latency_ms"] == 4.2


def test_configure_logging_includes_the_traceback_on_logger_exception(capsys) -> None:
    """logger.exception(...) keeps its traceback, not just the bare message."""
    configure_logging()

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("unhandled_exception")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["level"] == "ERROR"
    assert "ValueError: boom" in record["exception"]


def test_configure_logging_respects_the_requested_level(capsys) -> None:
    """DEBUG traces are silent by default and visible once the level is lowered."""
    configure_logging()
    logger.debug("scoring_started")
    assert capsys.readouterr().out == ""

    configure_logging(level="DEBUG")
    logger.debug("scoring_started")
    assert "scoring_started" in capsys.readouterr().out


def test_configure_logging_intercepts_stdlib_logging(capsys) -> None:
    """A stdlib log call (uvicorn, ...) is redirected through the same sink."""
    configure_logging()

    logging.getLogger("uvicorn.error").info("Uvicorn running on http://0.0.0.0:8000")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["level"] == "INFO"
    assert record["message"] == "Uvicorn running on http://0.0.0.0:8000"


def test_configure_logging_relays_a_level_unknown_to_loguru(capsys) -> None:
    """A stdlib level with no Loguru equivalent still reaches the sink, by number."""
    configure_logging()

    logging.getLogger("custom").log(25, "custom level message")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["message"] == "custom level message"
