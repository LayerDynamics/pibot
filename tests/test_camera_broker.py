"""T12.2.1 — CameraBroker: single capture loop, N async subscribers, drop-oldest overflow.

Tests:
  - One mocked source fans out to two subscribers; both receive every frame.
  - The source is constructed only once (one capture handle).
  - Unsubscribing stops delivery to that queue.
  - BrokerCamera adapter exposes synchronous .capture() for the autonomy consumer.
"""

from __future__ import annotations

import asyncio
from typing import Any


def _run(coro) -> Any:
    return asyncio.run(coro)


class _FakeCam:
    """Synchronous fake camera that records open/capture calls."""

    def __init__(self) -> None:
        self.open_count = 0
        self.capture_count = 0
        self._seq = 0

    def open(self) -> None:
        self.open_count += 1

    def capture(self) -> str:
        self.capture_count += 1
        self._seq += 1
        return f"IMG{self._seq}"


def test_fanout_two_subscribers_each_receive_every_frame() -> None:
    """Both subscribers receive the same set of frames (by seq)."""

    async def body() -> None:
        from agent.video import CameraBroker

        cam = _FakeCam()
        cam.open()

        broker = CameraBroker(cam, fps=100)
        q1 = broker.subscribe()
        q2 = broker.subscribe()

        await broker.start()

        # Wait for both queues to accumulate at least 3 frames.
        for _ in range(200):
            if q1.qsize() >= 3 and q2.qsize() >= 3:
                break
            await asyncio.sleep(0.01)

        await broker.stop()

        assert q1.qsize() >= 3, "subscriber 1 received no frames"
        assert q2.qsize() >= 3, "subscriber 2 received no frames"

        seqs1 = set()
        while not q1.empty():
            seqs1.add(q1.get_nowait().seq)

        seqs2 = set()
        while not q2.empty():
            seqs2.add(q2.get_nowait().seq)

        assert seqs1 == seqs2, "subscribers received different frames"

    _run(body())


def test_camera_opened_only_once() -> None:
    """The broker must not re-open the camera; only the caller's open() counts."""

    async def body() -> None:
        from agent.video import CameraBroker

        cam = _FakeCam()
        cam.open()  # opened by the caller — exactly once

        broker = CameraBroker(cam, fps=100)
        q1 = broker.subscribe()
        q2 = broker.subscribe()

        await broker.start()
        for _ in range(50):
            if cam.capture_count >= 2:
                break
            await asyncio.sleep(0.01)
        await broker.stop()

        assert cam.open_count == 1, f"camera was opened {cam.open_count} times (expected 1)"

    _run(body())


def test_unsubscribe_stops_delivery() -> None:
    """After unsubscribe, no further frames are placed on that queue."""

    async def body() -> None:
        from agent.video import CameraBroker

        cam = _FakeCam()
        cam.open()

        broker = CameraBroker(cam, fps=100)
        q = broker.subscribe()

        await broker.start()

        # Wait for at least one frame to confirm the broker is running.
        await asyncio.wait_for(q.get(), timeout=2.0)

        broker.unsubscribe(q)

        # Drain any frames that arrived before the unsubscribe propagated.
        while not q.empty():
            q.get_nowait()

        # Let the broker run for a bit more — nothing should arrive.
        await asyncio.sleep(0.05)
        await broker.stop()

        assert q.empty(), "frames delivered to queue after unsubscribe"

    _run(body())


def test_broker_camera_capture_returns_latest_frame() -> None:
    """BrokerCamera.capture() returns the latest frame via the subscriber queue."""

    async def body() -> None:
        from agent.video import BrokerCamera, CameraBroker

        cam = _FakeCam()
        cam.open()

        broker = CameraBroker(cam, fps=100)
        q = broker.subscribe()

        await broker.start()

        # Wait until at least one frame is queued.
        for _ in range(200):
            if not q.empty():
                break
            await asyncio.sleep(0.01)

        await broker.stop()

        bcam = BrokerCamera(q)
        frame_data = bcam.capture()
        assert frame_data is not None
        assert isinstance(frame_data, str) and frame_data.startswith("IMG")

    _run(body())


def test_drop_oldest_on_overflow_does_not_block_source() -> None:
    """A slow subscriber (queue full) drops frames, never backpressures the broker."""

    async def body() -> None:
        from agent.video import CameraBroker

        cam = _FakeCam()
        cam.open()

        broker = CameraBroker(cam, fps=200, maxsize=2)
        slow_q = broker.subscribe()

        await broker.start()

        # Run long enough for the broker to have produced >> maxsize frames.
        await asyncio.sleep(0.1)
        await broker.stop()

        # The broker must have captured many frames — not blocked at 2.
        assert cam.capture_count > 5, (
            f"broker stalled at maxsize: only {cam.capture_count} captures"
        )
        # The slow queue holds at most maxsize frames (dropped oldest).
        assert slow_q.qsize() <= 2

    _run(body())
