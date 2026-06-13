"""Camera-frame broker: one capture loop, N async subscribers (SPEC-3 §3.2 / M12.2 T12.2.1).

``CameraBroker`` owns a single camera handle and produces frames at ``fps`` to any number of
per-subscriber :class:`asyncio.Queue` instances. Queues are bounded (``maxsize``); when a
subscriber queue is full the oldest frame is dropped so the capture loop never blocks waiting
for a slow consumer. The autonomy loop and the ``/video`` WS endpoint each subscribe once and
consume independently — the camera device is opened exactly once.

``BrokerCamera`` wraps a subscriber queue and exposes a synchronous ``.capture()`` so the
existing :class:`~agent.autonomy.AutonomyController` /
:class:`~pibot.ml.pibot_environment.PibotEnvironment` interface keeps working without change
after the broker refactor.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Frame:
    """One captured frame from the broker."""

    seq: int
    ts: float
    data: Any  # raw numpy array (for autonomy) or whatever the camera returns


class CameraBroker:
    """Run one camera-capture loop; fan every frame out to all subscriber queues.

    Args:
        camera: Any object with a synchronous ``.capture()`` — must already be opened.
        fps:    Target capture rate.  The loop sleeps to maintain the period; passing 0
                disables sleeping (runs as fast as the camera allows).
        maxsize: Maximum frames held per subscriber queue.  When full the oldest is
                 dropped (drop-oldest policy) so the broker loop is never blocked.
    """

    def __init__(self, camera: Any, *, fps: int = 10, maxsize: int = 4) -> None:
        self._camera = camera
        self._period = 1.0 / fps if fps > 0 else 0.0
        self._maxsize = maxsize
        self._subscribers: list[asyncio.Queue[Frame]] = []
        self._task: asyncio.Task[None] | None = None
        self._seq = 0

    def subscribe(self) -> asyncio.Queue[Frame]:
        """Return a new bounded queue that receives every frame from this point on."""
        q: asyncio.Queue[Frame] = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Frame]) -> None:
        """Stop delivering frames to ``q``."""
        with contextlib.suppress(ValueError):
            self._subscribers.remove(q)

    async def start(self) -> None:
        """Start the background capture loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the capture loop and wait for it to finish."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        try:
            while True:
                t0 = asyncio.get_event_loop().time()
                data = await asyncio.to_thread(self._camera.capture)
                frame = Frame(seq=self._seq, ts=time.time(), data=data)
                self._seq += 1
                for q in list(self._subscribers):
                    if q.full():
                        with contextlib.suppress(asyncio.QueueEmpty):
                            q.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        q.put_nowait(frame)
                if self._period > 0:
                    elapsed = asyncio.get_event_loop().time() - t0
                    delay = max(0.0, self._period - elapsed)
                    if delay > 0:
                        await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass


class BrokerCamera:
    """Synchronous camera adapter backed by a :class:`CameraBroker` subscriber queue.

    Exposes ``.capture()`` so it is a drop-in replacement for any camera object used
    by :class:`~agent.autonomy.AutonomyController` /
    :class:`~pibot.ml.pibot_environment.PibotEnvironment`.  Calling ``.capture()``
    drains the queue and returns the *latest* available frame (drop-oldest semantics),
    or raises :class:`~pibot.ml.camera.CameraError` if no frame has arrived yet.

    The optional ``broker`` back-reference lets the app layer (``build_app`` /
    ``AgentState``) start the capture loop and make it available to the ``/video``
    endpoint without changing the two-element :py:data:`~agent.app.AutonomyFactory`
    return type.
    """

    def __init__(
        self,
        queue: asyncio.Queue[Frame],
        *,
        broker: CameraBroker | None = None,
    ) -> None:
        self._queue = queue
        self._broker = broker
        self._latest: Any = None

    @property
    def broker(self) -> CameraBroker | None:
        """The owning :class:`CameraBroker`; used by ``build_app`` for lifecycle management."""
        return self._broker

    def capture(self) -> Any:
        """Return the latest frame data from the subscriber queue.

        Drains all pending frames and returns the most recent.  Safe to call from the
        asyncio event-loop thread (uses ``get_nowait``).
        """
        while True:
            try:
                self._latest = self._queue.get_nowait().data
            except asyncio.QueueEmpty:
                break
        if self._latest is None:
            from pibot.ml.camera import CameraError

            raise CameraError("no frame available from broker yet")
        return self._latest


# ---------------------------------------------------------------------------
# JPEG encoding for the /video WS endpoint
# ---------------------------------------------------------------------------


def encode_jpeg(frame: Any, max_dim: int) -> tuple[bytes, int, int]:
    """Encode *frame* to JPEG, downscaling so ``max(w, h) <= max_dim``.

    *frame* may be a ``PIL.Image.Image`` or a numpy ``uint8`` array (HxWx3).
    Returns ``(jpeg_bytes, width, height)``.  Small frames are never upscaled.
    """
    from PIL import Image

    if isinstance(frame, Image.Image):
        img = frame.copy()
    else:
        import numpy as np

        img = Image.fromarray(np.asarray(frame, dtype="uint8"))

    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        w, h = img.size

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), w, h
