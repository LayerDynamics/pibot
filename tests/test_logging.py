"""T0.2 — structured logging (text + JSON) and the typed error hierarchy."""

from __future__ import annotations

import json
import logging

from pibot.errors import ConfigError, InventoryError, PibotError, UsageError
from pibot.logging import JsonFormatter, configure_logging, get_logger


def test_error_hierarchy_exit_codes() -> None:
    assert PibotError().exit_code == 1
    assert UsageError("bad args").exit_code == 2
    assert ConfigError("bad config").exit_code == 1
    assert InventoryError("missing").exit_code == 1
    # All suite errors share a common base for a single except clause.
    for err in (UsageError(), ConfigError(), InventoryError()):
        assert isinstance(err, PibotError)


def test_error_message_preserved() -> None:
    err = ConfigError("config.toml is malformed")
    assert str(err) == "config.toml is malformed"


def test_configure_logging_sets_level_and_single_handler() -> None:
    log = configure_logging(verbose=True)
    assert log.level == logging.DEBUG
    assert len(log.handlers) == 1
    # Reconfiguring must not stack handlers.
    log = configure_logging(verbose=False)
    assert log.level == logging.INFO
    assert len(log.handlers) == 1
    assert log.propagate is False


def test_json_formatter_emits_structured_record() -> None:
    fmt = JsonFormatter()
    record = logging.LogRecord(
        name="pibot.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="temp %d C",
        args=(81,),
        exc_info=None,
    )
    record.host = "192.168.1.99"  # an `extra=` field
    payload = json.loads(fmt.format(record))
    assert payload["level"] == "WARNING"
    assert payload["name"] == "pibot.test"
    assert payload["msg"] == "temp 81 C"
    assert payload["host"] == "192.168.1.99"


def test_get_logger_is_namespaced() -> None:
    assert get_logger().name == "pibot"
    assert get_logger("provision").name == "pibot.provision"
