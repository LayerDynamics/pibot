"""In-process closed-loop autonomy — the VLA drives through the agent's single safety gate.

`AutonomyController` runs the ``observe → infer → drive`` loop *inside* pibotd. Instead of
opening its own transport (the old standalone runner), it submits every action through the
shared :class:`~agent.control.TransportController` — so a policy drive is clamped, e-stop-gated,
and deadman-watched **identically to teleop**, and the agent's independent deadman ticker keeps
running even while an inference is in flight. Live policy-link health is recorded into the
shared :class:`~agent.telemetry.PolicyLink`, so it appears in ``/telemetry`` (and ``pibot
monitor``) — the integration the standalone runner could not provide.

Inference runs in a worker thread (:func:`asyncio.to_thread`) so a wedged policy server can
never block the event loop: telemetry keeps streaming and the deadman keeps ticking, so a
stalled policy still drops the robot to stop. The camera frame + action→drive mapping are
reused from the tested :class:`~pibot.ml.closed_loop.ClosedLoopEnvironment` (its synchronous
``submit`` is a capture buffer here; the real, async send goes through the controller).

This module imports no numpy/opencv/openpi at load — :func:`build_runtime` pulls them in lazily
only when autonomy actually starts, so the ml-import isolation guard keeps holding.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agent.control import ControlRejected
from pibot.ml.closed_loop import ClosedLoopEnvironment
from pibot.ml.state import VelocityState
from pibot.protocol.codec import Message

if TYPE_CHECKING:
    from agent.control import TransportController
    from agent.telemetry import PolicyLink


class AutonomyController:
    def __init__(
        self,
        controller: TransportController,
        policy_link: PolicyLink,
        *,
        camera: Any,
        policy: Any,
        prompt: str = "",
        control_hz: float = 20,
        max_speed: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._controller = controller
        self._link = policy_link
        self._policy = policy  # duck-typed: .infer(obs_dict) -> action vector
        self._max_speed = max_speed
        self._period = 1.0 / control_hz if control_hz > 0 else 0.0
        self._clock = clock
        self._velocity = VelocityState()  # state = last commanded velocity [v, ω] (OQ-2)
        self._outbox: list[Message] = []
        # The env's synchronous submit is a capture buffer; the real send is the async controller.
        self._env = ClosedLoopEnvironment(
            camera, self._velocity.vector, prompt, submit=self._capture
        )
        self._task: asyncio.Task[None] | None = None

    @property
    def policy_link(self) -> PolicyLink:
        return self._link

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _capture(self, msg: Message) -> tuple[bool, str]:
        self._outbox.append(msg)
        return True, "ok"

    def _govern(self, msg: Message) -> Message:
        """Apply the operator's speed cap before the shared gate (which re-clamps to hardware)."""
        if self._max_speed is None or msg.name != "drive":
            return msg
        v = max(-self._max_speed, min(self._max_speed, float(msg.args.get("v", 0.0))))
        return Message(msg.type, msg.seq, msg.name, {**msg.args, "v": v}, msg.reason)

    async def _drain(self) -> None:
        for msg in self._outbox:
            try:
                await self._controller.submit(self._govern(msg))
            except ControlRejected:
                pass  # e-stop latched / rate-limited — the gate did its job; keep looping
        self._outbox.clear()

    async def step(self) -> None:
        """One control cycle: observe → infer (off-thread) → gated drive → advance state."""
        obs = self._env.get_observation()
        t0 = self._clock()
        action = await asyncio.to_thread(self._policy.infer, obs)
        self._link.record_inference((self._clock() - t0) * 1000.0)
        self._outbox.clear()
        self._env.apply_action(action)  # maps to a drive (or nothing, if malformed)
        await self._drain()
        self._velocity.update(action)

    async def _run(self) -> None:
        try:
            self._outbox.clear()
            self._env.reset()  # begin from a known stop
            await self._drain()
            while True:
                await self.step()
                if self._period:
                    await asyncio.sleep(self._period)
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._outbox.clear()
        self._env.reset()  # always leave the robot stopped
        await self._drain()
        self._link.mark_disconnected()


def build_runtime(  # pragma: no cover - hardware: opencv camera + openpi websocket policy
    autonomy_config: dict[str, Any],
) -> tuple[Any, Any]:
    """Build the real (camera, policy) for an autonomy session — lazy cv2/openpi imports.

    Kept out of import time so ``agent.app`` stays free of the ml stack until autonomy runs.
    """
    from openpi_client import action_chunk_broker, websocket_client_policy

    from pibot.ml.camera import Camera

    camera = Camera(autonomy_config.get("camera_device", "/dev/video0"))
    camera.open()
    policy = action_chunk_broker.ActionChunkBroker(
        websocket_client_policy.WebsocketClientPolicy(
            host=autonomy_config["policy_host"], port=autonomy_config.get("policy_port", 8000)
        ),
        action_horizon=autonomy_config.get("action_horizon", 50),
    )
    return camera, policy
