"""Loguru configuration for structured JSON stdout logs."""

import inspect
import json
import logging
import traceback

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Redirect standard-library log records (uvicorn, ...) through Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Relay one stdlib log record to Loguru, preserving its call site."""
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _json_line(record: dict) -> str:
    """Render one log record as a single JSON line, bound fields included.

    A log pipeline (Alloy/Loki, see deploy/alloy/config.alloy) needs to
    parse fields without a fragile ad hoc format — that's what JSON is for.
    """
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        **record["extra"],
    }
    if record["exception"] is not None:
        payload["exception"] = "".join(traceback.format_exception(*record["exception"]))
    return json.dumps(payload, default=str)


def _sink(message) -> None:
    """Write one JSON-formatted record to stdout."""
    print(_json_line(message.record))


def configure_logging(level: str = "INFO") -> None:
    """Configure Loguru to emit structured JSON logs, including from stdlib logging.

    Redirects every standard-library logger (uvicorn's included) through
    Loguru so the whole process emits one consistent format instead of a mix
    of our lines and uvicorn's own. ``level`` defaults to ``INFO`` for a
    quiet production stream; pass ``DEBUG`` locally to see the per-step
    traces emitted while loading the model or scoring a request.
    """
    logger.remove()
    logger.add(_sink, level=level, backtrace=False, diagnose=False)

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in logging.root.manager.loggerDict:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = [_InterceptHandler()]
        stdlib_logger.propagate = False
