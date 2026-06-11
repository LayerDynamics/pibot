"""T4.2 — agent-central safety: e-stop gate, deadman watchdog, rate limit, stop-on-trip."""

from __future__ import annotations

from agent.safety import AgentSafety
from pibot.protocol.codec import Message, MessageType, decode


def _drive(seq: int = 1) -> Message:
    return Message(MessageType.COMMAND, seq, "drive", {"v": 0.5, "w": 0.0})


def _last(sent: list[bytes]) -> Message:
    return decode(sent[-1], "ascii")


def test_submit_clamps_and_sends() -> None:
    sent: list[bytes] = []
    s = AgentSafety(sent.append)
    ok, reason = s.submit(Message(MessageType.COMMAND, 1, "drive", {"v": 5.0, "w": 0.0}))
    assert ok is True and reason == "ok"
    assert _last(sent).args["v"] == 1.0  # clamped to Limits() max


def test_estop_blocks_motion_and_emits_stop() -> None:
    sent: list[bytes] = []
    now = [0.0]
    s = AgentSafety(
        sent.append, max_rate_hz=0, clock=lambda: now[0]
    )  # rate limit off; testing e-stop
    assert s.submit(_drive())[0] is True

    s.trip_estop()
    assert _last(sent).name == "stop"  # tripping emits a stop frame
    assert s.latched is True

    ok, reason = s.submit(_drive())
    assert ok is False and reason == "estop"
    assert s.submit(Message(MessageType.COMMAND, 2, "stop", {}))[0] is True  # stop still allowed

    s.resume()
    assert s.latched is False
    assert s.submit(_drive())[0] is True


def test_watchdog_emits_stop_on_expiry_once() -> None:
    sent: list[bytes] = []
    now = [0.0]
    s = AgentSafety(sent.append, deadman_ms=300, clock=lambda: now[0])
    s.submit(_drive())  # feeds watchdog at t=0
    now[0] = 0.1
    s.tick()
    assert _last(sent).name == "drive"  # not yet expired

    now[0] = 0.4  # 400 ms since last command > 300 ms
    s.tick()
    assert _last(sent).name == "stop"

    count = len(sent)
    now[0] = 0.5
    s.tick()
    assert len(sent) == count  # does not re-emit stop every tick


def test_rate_limit_drops_over_rate_motion() -> None:
    sent: list[bytes] = []
    now = [0.0]
    s = AgentSafety(sent.append, max_rate_hz=10, clock=lambda: now[0])  # min 100 ms apart
    assert s.submit(_drive())[0] is True
    ok, reason = s.submit(_drive())
    assert ok is False and reason == "rate"
    now[0] = 0.2
    assert s.submit(_drive())[0] is True


def test_ping_is_not_rate_limited_and_feeds_watchdog() -> None:
    sent: list[bytes] = []
    now = [0.0]
    s = AgentSafety(sent.append, max_rate_hz=10, deadman_ms=300, clock=lambda: now[0])
    assert s.submit(Message(MessageType.COMMAND, 1, "ping", {}))[0] is True
    assert s.submit(Message(MessageType.COMMAND, 2, "ping", {}))[0] is True  # no rate limit
    now[0] = 0.2
    s.tick()
    assert _last(sent).name == "ping"  # watchdog was fed by ping; no stop yet
