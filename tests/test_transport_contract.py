"""T3.2 — Transport ABC contract, checked against the in-memory loopback backend."""

from __future__ import annotations

import time

import pytest
from helpers import assert_transport_contract

from pibot.transport.base import TransportError
from pibot.transport.loopback import LoopbackTransport
from pibot.transport.responder import ResponderTransport


def test_loopback_satisfies_contract() -> None:
    assert_transport_contract(LoopbackTransport)


def test_send_before_open_raises() -> None:
    t = LoopbackTransport()
    with pytest.raises(TransportError):
        t.send(b">1,ping*5B\n")


def test_recv_before_open_raises() -> None:
    t = LoopbackTransport()
    with pytest.raises(TransportError):
        t.recv(0.01)


def test_reassembles_partial_writes() -> None:
    # Two frames delivered in awkward chunks must come back out whole, in order.
    t = LoopbackTransport()
    t.open()
    t.feed_raw(b">1,pi")
    assert t.recv(0.01) is None  # incomplete frame -> nothing yet
    t.feed_raw(b"ng*5B\n>2,st")
    assert t.recv(0.5) == b">1,ping*5B\n"
    assert t.recv(0.01) is None  # second frame still incomplete
    t.feed_raw(b"op*1A\n")
    assert t.recv(0.5) == b">2,stop*1A\n"


# ── Busy-loop regression (T12.2 pre-fix) ────────────────────────────────────
# Both no-hardware backends must pace idle recv() calls; previously they
# returned None instantly, causing _reader() to spin at ~112 % CPU on the Pi.

TIMEOUT = 0.05  # 50 ms — fast enough for CI, long enough to measure


def _idle_recv_paces(transport_cls, **kw) -> None:  # type: ignore[type-arg]
    """Idle recv must block for ≥ TIMEOUT - 5 ms; buffered recv must return fast."""
    t = transport_cls(**kw)
    t.open()

    # idle: no data → must wait
    t0 = time.monotonic()
    result = t.recv(TIMEOUT)
    elapsed = time.monotonic() - t0
    assert result is None
    assert elapsed >= TIMEOUT - 0.005, (
        f"{transport_cls.__name__}.recv({TIMEOUT}) returned in {elapsed:.4f}s — "
        "busy-loop regression: recv must wait for timeout when idle"
    )

    t.close()


def _buffered_recv_fast(transport_cls, send_frame: bytes, **kw) -> None:  # type: ignore[type-arg]
    """Buffered recv must return without waiting the full timeout."""
    t = transport_cls(**kw)
    t.open()
    t.send(send_frame)

    t0 = time.monotonic()
    result = t.recv(1.0)  # long timeout — must NOT sleep for 1 s
    elapsed = time.monotonic() - t0
    assert result is not None, f"{transport_cls.__name__}.recv returned None for buffered frame"
    assert elapsed < 0.1, (
        f"{transport_cls.__name__}.recv(1.0) took {elapsed:.4f}s on buffered frame — "
        "latency regression: must return immediately when a frame is buffered"
    )

    t.close()


def test_loopback_idle_recv_paces() -> None:
    _idle_recv_paces(LoopbackTransport)


def test_loopback_buffered_recv_fast() -> None:
    t = LoopbackTransport()
    t.open()
    t.send(b">1,ping*5B\n")

    t0 = time.monotonic()
    result = t.recv(1.0)
    elapsed = time.monotonic() - t0
    assert result == b">1,ping*5B\n"
    assert elapsed < 0.1, f"buffered recv took {elapsed:.4f}s — latency regression"

    t.close()


def test_responder_idle_recv_paces() -> None:
    _idle_recv_paces(ResponderTransport)


def test_responder_buffered_recv_fast() -> None:
    # Send a ping → EchoResponder feeds ACK back synchronously → frame is buffered before recv.
    _buffered_recv_fast(ResponderTransport, b">1,ping*5B\n")
