"""Structured logging for the PiBot Control Suite.

Two output modes share one logger tree rooted at ``pibot``:

* human text (default) — ``LEVEL message`` on stderr
* JSON (``--log-json``) — one JSON object per line, including any ``extra=`` fields

so operators get readable output and scripts/CI get machine-parseable logs.
"""

from __future__ import annotations

import json
import logging
import sys

ROOT_NAME = "pibot"

# LogRecord attributes that are intrinsic to the record; anything else on the
# record's __dict__ was supplied via ``logger.info(..., extra={...})`` and is
# promoted to a top-level field in JSON output.
_STD_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object, including extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD_RECORD_KEYS:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(verbose: bool = False, json_output: bool = False) -> logging.Logger:
    """Configure and return the suite's root logger. Idempotent (no handler stacking)."""
    logger = logging.getLogger(ROOT_NAME)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced child logger, e.g. ``get_logger("provision")``."""
    if not name:
        return logging.getLogger(ROOT_NAME)
    return logging.getLogger(f"{ROOT_NAME}.{name}")
