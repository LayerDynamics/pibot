"""T3.7 — one-shot `cmd` / `estop`: build, clamp, send, await ACK."""

from __future__ import annotations

import pytest

from pibot.config import Config
from pibot.control import oneshot
from pibot.control.safety import EStop
from pibot.errors import ConnectionError, UsageError
from pibot.inventory import Inventory, InventoryRecord
from pibot.protocol.codec import Message, MessageType, decode
from pibot.transport.responder import ResponderTransport


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


# ---- message building ----------------------------------------------------


def test_build_message_drive() -> None:
    msg = oneshot.build_message("drive", ["0.5", "0.0"], 1)
    assert msg == Message(MessageType.COMMAND, 1, "drive", {"v": 0.5, "w": 0.0})


def test_build_message_servo_types() -> None:
    msg = oneshot.build_message("servo", ["1", "90"], 2)
    assert msg.args == {"id": 1, "deg": 90.0}


def test_build_message_unknown_command() -> None:
    with pytest.raises(UsageError):
        oneshot.build_message("teleport", [], 1)


def test_build_message_bad_arity() -> None:
    with pytest.raises(UsageError):
        oneshot.build_message("drive", ["0.5"], 1)  # needs v and w


# ---- cmd end-to-end via the responder transport --------------------------


def test_cmd_ping_acks() -> None:
    t = ResponderTransport()
    assert oneshot.cmd("pibot", "ping", [], cfg=Config(), inventory=_inv(), transport=t) == 0


def test_cmd_drive_is_clamped_before_send() -> None:
    t = ResponderTransport()
    oneshot.cmd("pibot", "drive", ["5.0", "-9.0"], cfg=Config(), inventory=_inv(), transport=t)
    sent = decode(t.sent[0], "ascii")
    assert sent.args == {"v": 1.0, "w": -2.0}  # clamped to Limits() maxima


def test_cmd_json_output(capsys) -> None:
    t = ResponderTransport()
    oneshot.cmd("pibot", "ping", [], cfg=Config(), inventory=_inv(), transport=t, as_json=True)
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "ping"
    assert payload["target"] == "192.168.1.99"


def test_cmd_refuses_motion_when_estopped() -> None:
    t = ResponderTransport()
    latched = EStop()
    latched.trip()
    with pytest.raises(UsageError, match="e-stop"):
        oneshot.cmd(
            "pibot",
            "drive",
            ["0.5", "0.0"],
            cfg=Config(),
            inventory=_inv(),
            transport=t,
            estop_state=latched,
        )


def test_estop_sends_estop_command() -> None:
    t = ResponderTransport()
    assert oneshot.estop("pibot", cfg=Config(), inventory=_inv(), transport=t) == 0
    assert decode(t.sent[0], "ascii").name == "estop"


# ---- send_command failure modes ------------------------------------------


class _SilentTransport(ResponderTransport):
    def send(self, frame: bytes) -> None:  # accepts but never replies
        self.sent.append(frame)


def test_send_command_times_out_without_ack() -> None:
    t = _SilentTransport()
    t.open()
    cfg = Config(cmd_timeout=0.05)
    with pytest.raises(ConnectionError, match="no ACK"):
        oneshot.cmd("pibot", "ping", [], cfg=cfg, inventory=_inv(), transport=t)


def test_send_command_raises_on_nak() -> None:
    # A bad-CRC frame would NAK; here we drive a NAK by latching estop on the responder
    # side via a custom transport that NAKs motion.
    from pibot.protocol.codec import encode

    class _NakTransport(ResponderTransport):
        def send(self, frame: bytes) -> None:
            self.sent.append(frame)
            msg = decode(frame, "ascii")
            self._rx.feed(encode(Message(MessageType.NAK, msg.seq, reason="estop"), "ascii"))

    t = _NakTransport()
    t.open()
    with pytest.raises(ConnectionError, match="estop"):
        oneshot.cmd("pibot", "motor", ["0", "100"], cfg=Config(), inventory=_inv(), transport=t)
