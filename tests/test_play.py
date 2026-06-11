"""T5.6 — pibot play: parse a motion sequence, dispatch on schedule through safety gates."""

from __future__ import annotations

import asyncio

import pytest

from pibot.control.sequence import SequenceError, Step, load_sequence, play

SEQ_YAML = """
- {at: 1.0, cmd: stop}
- {at: 0.0, cmd: drive, args: {v: 0.5, w: 0.0}}
- {at: 0.5, cmd: drive, args: {v: 0.0, w: 1.0}}
"""


def test_load_sequence_parses_and_sorts_by_time() -> None:
    steps = load_sequence(SEQ_YAML)
    assert [s.at for s in steps] == [0.0, 0.5, 1.0]  # sorted
    assert steps[0] == Step(0.0, "drive", {"v": 0.5, "w": 0.0})
    assert steps[-1].cmd == "stop"


def test_load_sequence_accepts_json_too() -> None:
    # JSON is a YAML subset, so the same loader reads a .json sequence.
    steps = load_sequence('[{"at": 0, "cmd": "ping"}]')
    assert steps == [Step(0.0, "ping", {})]


def test_load_sequence_rejects_malformed() -> None:
    with pytest.raises(SequenceError):
        load_sequence("- {at: 0.0}")  # missing 'cmd'
    with pytest.raises(SequenceError):
        load_sequence("not: a-list")  # top-level not a list


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class _RecordingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []
        self.estopped = False

    async def send_command(self, cmd: str, args: dict | None = None) -> dict:
        self.sent.append((cmd, args or {}))
        return {"ack": True}

    async def estop(self) -> dict:
        self.estopped = True
        self.sent.append(("estop", {}))
        return {"estop": True}


def _driver(clock: _FakeClock):
    async def fake_sleep(dt: float) -> None:
        clock.t += dt  # virtual time advances only when the scheduler sleeps

    return fake_sleep


def test_play_dispatches_in_time_order() -> None:
    clock = _FakeClock()
    client = _RecordingClient()
    steps = load_sequence(SEQ_YAML)

    asyncio.run(play(client, steps, keepalive_hz=10, clock=clock, sleep=_driver(clock)))

    kinds = [c for c, _ in client.sent]
    assert kinds[0] == "drive"  # first scheduled command
    assert kinds[-1] == "stop"  # last scheduled command
    # the middle turn-in-place command was issued
    assert ("drive", {"v": 0.0, "w": 1.0}) in client.sent


def test_play_keeps_watchdog_alive_between_steps() -> None:
    """A 1 s gap at 10 Hz keepalive re-sends the held motion many times, feeding the deadman."""
    clock = _FakeClock()
    client = _RecordingClient()
    steps = [Step(0.0, "drive", {"v": 0.5, "w": 0.0}), Step(1.0, "stop", {})]

    asyncio.run(play(client, steps, keepalive_hz=10, clock=clock, sleep=_driver(clock)))

    drive_count = sum(1 for c, _ in client.sent if c == "drive")
    assert drive_count >= 8  # held + repeated, not a single dispatch


def test_play_estop_aborts_sequence() -> None:
    clock = _FakeClock()
    client = _RecordingClient()
    steps = [
        Step(0.0, "drive", {"v": 0.5, "w": 0.0}),
        Step(0.5, "estop", {}),
        Step(1.0, "drive", {"v": 1.0, "w": 0.0}),  # must NOT run after e-stop
    ]

    rc = asyncio.run(play(client, steps, keepalive_hz=10, clock=clock, sleep=_driver(clock)))

    assert client.estopped is True
    assert rc != 0  # aborted
    # the post-estop drive was never dispatched
    assert ("drive", {"v": 1.0, "w": 0.0}) not in client.sent


def test_play_aborts_when_agent_rejects_with_estop() -> None:
    clock = _FakeClock()

    class _RejectingClient(_RecordingClient):
        async def send_command(self, cmd: str, args: dict | None = None) -> dict:
            self.sent.append((cmd, args or {}))
            return {"rejected": "estop"}  # agent latched e-stop out-of-band

    client = _RejectingClient()
    steps = [Step(0.0, "drive", {"v": 0.5}), Step(0.5, "drive", {"v": 0.9})]
    rc = asyncio.run(play(client, steps, keepalive_hz=10, clock=clock, sleep=_driver(clock)))
    assert rc != 0
    assert ("drive", {"v": 0.9}) not in client.sent
