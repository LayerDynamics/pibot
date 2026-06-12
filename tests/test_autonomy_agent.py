"""In-process autonomy: the VLA drives through the agent's single TransportController.

`AutonomyController` runs the observe→infer→drive loop *inside* pibotd, submitting every
action through the shared `TransportController.submit` (the same clamp + latched e-stop +
deadman teleop uses) and feeding the shared `PolicyLink` so the live policy-link health shows
up in `/telemetry`. Inference runs in a worker thread so a stalled policy can't block the
event loop — the controller's own deadman ticker keeps running. These unit tests drive a
single `step()` against a fake controller/camera/policy; the full agent path is exercised in
`tests/test_agent_endpoints.py`.
"""

from __future__ import annotations

import asyncio
import threading

from agent.autonomy import AutonomyController
from agent.control import ControlRejected, TransportController
from agent.telemetry import PolicyLink
from pibot.protocol.codec import Message, MessageType, decode
from pibot.transport.responder import ResponderTransport


class _Cam:
    def capture(self) -> str:
        return "IMG"


class _Policy:
    """A fake policy whose ``infer`` returns a fixed action vector (the broker's shape)."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec
        self.calls = 0

    def infer(self, obs: dict) -> list[float]:
        self.calls += 1
        return list(self._vec)


class _FakeController:
    def __init__(self, *, reject: str | None = None) -> None:
        self.sent: list[Message] = []
        self._reject = reject

    async def submit(self, msg: Message, *, timeout: float = 1.0) -> Message:
        if self._reject is not None:
            raise ControlRejected(self._reject)
        self.sent.append(msg)
        return Message(MessageType.ACK, msg.seq, "ack", {})


def _ctrl(controller, policy, *, max_speed=None, prompt="go") -> AutonomyController:
    link = PolicyLink()
    auto = AutonomyController(
        controller,
        link,
        camera=_Cam(),
        policy=policy,
        prompt=prompt,
        control_hz=0,
        max_speed=max_speed,
    )
    return auto


def _run(coro):
    return asyncio.run(coro)


def test_step_submits_a_drive_and_records_inference() -> None:
    async def body() -> None:
        fc = _FakeController()
        auto = _ctrl(fc, _Policy([0.5, -0.2]))
        await auto.step()
        assert len(fc.sent) == 1
        cmd = fc.sent[0]
        assert cmd.name == "drive" and cmd.args == {"v": 0.5, "w": -0.2}
        snap = auto.policy_link.snapshot()
        assert snap["connected"] is True
        assert snap["last_inference_ms"] is not None

    _run(body())


def test_estop_rejection_does_not_crash_the_loop() -> None:
    # A latched e-stop makes submit raise ControlRejected; the loop must absorb it and keep going.
    async def body() -> None:
        fc = _FakeController(reject="estop")
        policy = _Policy([0.5, 0.0])
        auto = _ctrl(fc, policy)
        await auto.step()  # must not raise
        assert fc.sent == []  # nothing actuated
        assert policy.calls == 1  # inference still ran (the gate, not the policy, blocked)

    _run(body())


def test_max_speed_governs_before_the_gate() -> None:
    async def body() -> None:
        fc = _FakeController()
        auto = _ctrl(fc, _Policy([5.0, 0.0]), max_speed=0.3)
        await auto.step()
        assert fc.sent[0].args["v"] == 0.3  # pre-clamped to the governor

    _run(body())


def test_malformed_action_actuates_nothing() -> None:
    async def body() -> None:
        fc = _FakeController()
        auto = _ctrl(fc, _Policy([0.5]))  # missing w
        await auto.step()
        assert fc.sent == []

    _run(body())


def test_stop_submits_a_stop_and_disconnects() -> None:
    async def body() -> None:
        fc = _FakeController()
        auto = _ctrl(fc, _Policy([0.5, 0.0]))
        await auto.stop()
        assert fc.sent[-1].name == "stop"
        assert auto.policy_link.snapshot()["connected"] is False

    _run(body())


class _BlockingPolicy:
    """Returns one drive, then hangs the inference thread — a wedged policy server."""

    def __init__(self, drive: list[float]) -> None:
        self._drive = drive
        self._event = threading.Event()
        self.calls = 0
        self.blocked = False

    def infer(self, obs: dict) -> list[float]:
        self.calls += 1
        if self.calls == 1:
            return list(self._drive)
        self.blocked = True
        self._event.wait()  # hang the worker thread until released
        return list(self._drive)

    def release(self) -> None:
        self._event.set()


def test_stalled_policy_still_drops_to_stop_via_the_agent_deadman() -> None:
    # The headline of the in-process design: because inference runs OFF the control thread, a
    # wedged infer() can't block the agent's deadman ticker — it fires a stop within watchdog_ms
    # even though the loop is stuck mid-inference. (If a future change called infer() inline, this
    # breaks — which is the whole point of the regression.)
    async def body() -> None:
        transport = ResponderTransport()
        controller = TransportController(transport, deadman_ms=50, tick_interval=0.02)
        await controller.start()
        policy = _BlockingPolicy([0.5, 0.0])
        auto = AutonomyController(
            controller, PolicyLink(), camera=_Cam(), policy=policy, prompt="go", control_hz=50
        )
        auto.start()
        try:
            await asyncio.sleep(0.25)  # 1st drive goes out; 2nd infer hangs; deadman must fire
            assert policy.blocked, "the test must actually be stalled mid-inference"
            names = [decode(f).name for f in transport.sent]
            assert "drive" in names
            after_drive = names[names.index("drive") + 1 :]
            # the only sender after the (blocked) drive is the deadman ticker — so a stop here
            # proves the agent halted the robot while inference was wedged.
            assert "stop" in after_drive, "agent deadman must stop the robot during a policy stall"
        finally:
            policy.release()
            await auto.stop()
            await controller.stop()

    _run(body())
