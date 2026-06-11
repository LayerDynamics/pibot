"""T0.3 — minimal TOML writer; correctness proven by round-tripping through tomllib."""

from __future__ import annotations

import pytest

from pibot import tomlio


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"a": 1, "b": "x", "c": True, "f": 1.5},
        {"empty": [], "nums": [1, 2, 3], "words": ["a", "b"]},
        {"defaults": {"user": "ryan", "rate": 20}, "agent": {"bind": "127.0.0.1:8787"}},
        {
            "host": [
                {"alias": "pibot", "ip": "192.168.1.99", "port": 22, "pi": True},
                {"alias": "spare", "ip": "10.147.20.44"},
            ],
            "version": 1,
        },
        {"tricky": 'has "quotes" and \\backslash and unicodé'},
    ],
)
def test_round_trip(data: dict) -> None:
    rendered = tomlio.dumps(data)
    assert tomlio.loads(rendered) == data


def test_none_values_are_omitted() -> None:
    rendered = tomlio.dumps({"present": "yes", "absent": None})
    parsed = tomlio.loads(rendered)
    assert parsed == {"present": "yes"}


def test_dump_and_load_file(tmp_path) -> None:
    path = tmp_path / "x.toml"
    data = {"k": "v", "section": {"n": 3}}
    tomlio.dump(data, path)
    assert tomlio.load(path) == data


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert tomlio.load(tmp_path / "nope.toml") == {}
