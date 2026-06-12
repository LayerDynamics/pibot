"""T3.6 — safety primitives: command clamping, latched e-stop, deadman watchdog."""

from __future__ import annotations

from pibot.control.safety import EStop, Limits, Watchdog, clamp_command
from pibot.protocol.codec import Message, MessageType


def _cmd(name: str, **args) -> Message:
    return Message(MessageType.COMMAND, 1, name, args)


# ---- clamping ------------------------------------------------------------


def test_clamp_drive_bounds_velocity() -> None:
    lim = Limits(max_v=1.0, max_w=2.0)
    out = clamp_command(_cmd("drive", v=5.0, w=-9.0), lim)
    assert out.args == {"v": 1.0, "w": -2.0}


def test_clamp_drive_within_limits_unchanged() -> None:
    lim = Limits(max_v=1.0, max_w=2.0)
    out = clamp_command(_cmd("drive", v=0.4, w=-1.0), lim)
    assert out.args == {"v": 0.4, "w": -1.0}


def test_clamp_servo_range() -> None:
    lim = Limits(servo_min=0.0, servo_max=180.0)
    assert clamp_command(_cmd("servo", id=1, deg=270), lim).args["deg"] == 180.0
    assert clamp_command(_cmd("servo", id=1, deg=-5), lim).args["deg"] == 0.0


def test_clamp_motor_pwm() -> None:
    lim = Limits(max_pwm=255)
    assert clamp_command(_cmd("motor", id=1, pwm=1000), lim).args["pwm"] == 255
    assert clamp_command(_cmd("motor", id=1, pwm=-1000), lim).args["pwm"] == -255


def test_clamp_leaves_non_motion_commands_alone() -> None:
    lim = Limits()
    msg = _cmd("ping")
    assert clamp_command(msg, lim) == msg
    assert clamp_command(_cmd("set", param="k", value=9.0), lim).args == {
        "param": "k",
        "value": 9.0,
    }


# ---- e-stop --------------------------------------------------------------


def test_estop_latches_and_rejects_motion() -> None:
    e = EStop()
    assert e.latched is False
    assert e.allows(_cmd("drive", v=0.5, w=0.0)) is True
    e.trip()
    assert e.latched is True
    assert e.allows(_cmd("drive", v=0.5, w=0.0)) is False
    assert e.allows(_cmd("motor", id=1, pwm=100)) is False
    # safe commands still pass while latched
    assert e.allows(_cmd("stop")) is True
    assert e.allows(_cmd("estop")) is True
    assert e.allows(_cmd("ping")) is True


def test_estop_resume_clears_latch() -> None:
    e = EStop()
    e.trip()
    e.resume()
    assert e.latched is False
    assert e.allows(_cmd("drive", v=0.5, w=0.0)) is True


# ---- watchdog ------------------------------------------------------------


def test_watchdog_trips_after_deadman() -> None:
    now = [0.0]
    wd = Watchdog(deadman_ms=300, clock=lambda: now[0])
    assert wd.expired() is False
    now[0] = 0.25
    assert wd.expired() is False
    now[0] = 0.40  # 400 ms since last feed > 300 ms
    assert wd.expired() is True


def test_watchdog_feed_resets() -> None:
    now = [0.0]
    wd = Watchdog(deadman_ms=300, clock=lambda: now[0])
    now[0] = 0.40
    assert wd.expired() is True
    wd.feed()  # fed at t=0.40
    assert wd.expired() is False
    now[0] = 0.80  # 400 ms after the feed
    assert wd.expired() is True
