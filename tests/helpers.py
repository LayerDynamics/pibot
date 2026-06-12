"""Shared test helpers (not collected by pytest — no ``test_`` prefix)."""

from __future__ import annotations

from collections.abc import Callable


def assert_transport_contract(make_transport: Callable[[], object]) -> None:
    """Assert any Transport backend satisfies the open/send/recv/close contract.

    Reused by the loopback, serial (pty), and TCP backend tests so every transport is
    held to the same observable behaviour.
    """
    t = make_transport()
    assert t.is_open is False  # type: ignore[attr-defined]

    t.open()  # type: ignore[attr-defined]
    assert t.is_open is True  # type: ignore[attr-defined]
    info = t.info  # type: ignore[attr-defined]
    assert isinstance(info, dict) and "backend" in info

    frame = b">1,ping*5B\n"
    t.send(frame)  # type: ignore[attr-defined]
    got = t.recv(0.5)  # type: ignore[attr-defined]
    assert got is not None
    assert got.rstrip(b"\r\n") == frame.rstrip(b"\r\n")

    # Nothing more buffered -> recv returns None within the timeout.
    assert t.recv(0.05) is None  # type: ignore[attr-defined]

    t.close()  # type: ignore[attr-defined]
    assert t.is_open is False  # type: ignore[attr-defined]
