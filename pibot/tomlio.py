"""Minimal TOML read/write for the suite's own config and inventory files.

The standard library ships ``tomllib`` for reading but no writer. Rather than add a
third-party dependency to the dependency-light host CLI, this module provides a small
writer that covers exactly the value shapes the suite persists: scalars (str/int/
float/bool), inline arrays of scalars, nested tables, and arrays of tables. Its
correctness is pinned by round-tripping every shape back through ``tomllib`` in the
tests — anything ``dumps`` emits, ``tomllib`` must parse back to the original object.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def loads(text: str) -> dict[str, Any]:
    """Parse a TOML string into a dict."""
    return tomllib.loads(text)


def load(path: str | Path) -> dict[str, Any]:
    """Read a TOML file, returning ``{}`` if it does not exist."""
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("rb") as fh:
        return tomllib.load(fh)


def dumps(obj: Mapping[str, Any]) -> str:
    """Serialize a mapping to TOML text. ``None`` values are omitted (TOML has no null)."""
    lines: list[str] = []
    _emit_table(obj, [], lines)
    return ("\n".join(lines) + "\n") if lines else ""


def dump(obj: Mapping[str, Any], path: str | Path) -> None:
    """Write a mapping to ``path`` as TOML text."""
    Path(path).write_text(dumps(obj), encoding="utf-8")


def _is_table_array(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str | bytes)
        and len(value) > 0
        and all(isinstance(item, Mapping) for item in value)
    )


def _emit_table(table: Mapping[str, Any], prefix: list[str], lines: list[str]) -> None:
    scalars: list[tuple[str, Any]] = []
    sub_tables: list[tuple[str, Mapping[str, Any]]] = []
    table_arrays: list[tuple[str, Sequence[Any]]] = []

    for key, value in table.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            sub_tables.append((key, value))
        elif _is_table_array(value):
            table_arrays.append((key, value))
        else:
            scalars.append((key, value))

    for key, value in scalars:
        lines.append(f"{_format_key(key)} = {_format_value(value)}")

    for key, value in sub_tables:
        header = prefix + [key]
        lines.append("")
        lines.append(f"[{_join_header(header)}]")
        _emit_table(value, header, lines)

    for key, value in table_arrays:
        header = prefix + [key]
        for item in value:
            lines.append("")
            lines.append(f"[[{_join_header(header)}]]")
            _emit_table(item, header, lines)


def _join_header(parts: list[str]) -> str:
    return ".".join(_format_key(p) for p in parts)


def _format_key(key: str) -> str:
    return key if _BARE_KEY.fullmatch(key) else json.dumps(key)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        # JSON string escaping is a valid subset of TOML basic-string escaping.
        return json.dumps(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")
