"""T3.2 — Transport ABC contract, checked against the in-memory loopback backend."""

from __future__ import annotations

import pytest
from helpers import assert_transport_contract

from pibot.transport.base import TransportError
from pibot.transport.loopback import LoopbackTransport


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
