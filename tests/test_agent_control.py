"""T4.3 — the agent's transport controller: serialized sends, e-stop preempt, ack routing."""

from __future__ import annotations

import asyncio

import pytest

from agent.control import ControlRejected, TransportController
from pibot.protocol.codec import Message, MessageType, decode
from pibot.transport.responder import ResponderTransport


def _run(coro) -> None:
    asyncio.run(coro)


def _drive() -> Message:
    return Message(MessageType.COMMAND, 0, "drive", {"v": 0.5, "w": 0.0})


def _ping() -> Message:
    return Message(MessageType.COMMAND, 0, "ping", {})


def test_submit_returns_ack() -> None:
    async def body() -> None:
        c = TransportController(ResponderTransport(), max_rate_hz=0)
        await c.start()
        try:
            reply = await c.submit(_ping())
            assert reply.type is MessageType.ACK
        finally:
            await c.stop()

    _run(body())


def test_concurrent_submits_all_acked_with_unique_seqs() -> None:
    async def body() -> None:
        t = ResponderTransport()
        c = TransportController(t, max_rate_hz=0)
        await c.start()
        try:
            replies = await asyncio.gather(*[c.submit(_drive()) for _ in range(10)])
            assert all(r.type is MessageType.ACK for r in replies)
            assert len({r.seq for r in replies}) == 10  # single owner assigned unique seqs
            # every frame on the wire is a complete, decodable command (no interleaving)
            for frame in t.sent:
                assert frame.endswith(b"\n")
                decode(frame, "ascii")
        finally:
            await c.stop()

    _run(body())


def test_estop_preempts_and_blocks_subsequent_motion() -> None:
    async def body() -> None:
        t = ResponderTransport()
        c = TransportController(t)
        await c.start()
        try:
            c.estop()
            assert any(decode(f, "ascii").name == "stop" for f in t.sent)
            with pytest.raises(ControlRejected):
                await c.submit(_drive())
        finally:
            await c.stop()

    _run(body())


def test_telemetry_is_routed_to_callback() -> None:
    async def body() -> None:
        got: list[Message] = []
        c = TransportController(ResponderTransport(), on_telemetry=got.append, max_rate_hz=0)
        await c.start()
        try:
            await c.submit(_ping())  # the responder answers ping with battery telemetry
            for _ in range(20):
                if any(m.name == "battery" for m in got):
                    break
                await asyncio.sleep(0.01)
            assert any(m.name == "battery" and m.type is MessageType.TELEMETRY for m in got)
        finally:
            await c.stop()

    _run(body())


def test_nak_routed_back_to_sender() -> None:
    async def body() -> None:
        # Latch e-stop on the robot side via a transport that NAKs motion.
        class _NakTransport(ResponderTransport):
            def send(self, frame: bytes) -> None:
                self.sent.append(frame)
                from pibot.protocol.codec import encode

                msg = decode(frame, "ascii")
                if msg.name in ("drive", "motor", "servo"):
                    self._rx.feed(
                        encode(Message(MessageType.NAK, msg.seq, reason="estop"), "ascii")
                    )
                else:
                    for out in self._responder.feed(frame):
                        self._rx.feed(out)

        c = TransportController(_NakTransport(), max_rate_hz=0)
        await c.start()
        try:
            reply = await c.submit(_drive())
            assert reply.type is MessageType.NAK and reply.reason == "estop"
        finally:
            await c.stop()

    _run(body())
