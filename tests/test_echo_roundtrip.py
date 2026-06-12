"""T3.5 — codec round-trips against the firmware-mirror EchoResponder over real
transports (TCP socket + a pty serial port). This is the host-side CI stand that
stands in for the Arduino when no hardware is attached."""

from __future__ import annotations

import os
import select
import socket
import threading
import tty

import pytest

from pibot.control.echo import EchoResponder
from pibot.protocol.codec import Message, MessageType, decode, encode
from pibot.transport.serial import SerialTransport
from pibot.transport.tcp import TcpTransport


def _ping(seq: int) -> bytes:
    return encode(Message(MessageType.COMMAND, seq, "ping"), "ascii")


def _drive(seq: int) -> bytes:
    return encode(Message(MessageType.COMMAND, seq, "drive", {"v": 0.5, "w": 0.0}), "ascii")


# ---- responder-backed TCP server ----------------------------------------


class _ResponderServer:
    def __init__(self) -> None:
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        self._srv.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except (TimeoutError, OSError):
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        responder = EchoResponder()
        try:
            while not self._stop:
                data = conn.recv(4096)
                if not data:
                    break
                for out in responder.feed(data):
                    conn.sendall(out)
        except OSError:
            pass

    def stop(self) -> None:
        self._stop = True
        self._srv.close()


def test_roundtrip_over_tcp() -> None:
    srv = _ResponderServer()
    try:
        t = TcpTransport("127.0.0.1", srv.port)
        t.open()
        t.send(_ping(7))
        ack = decode(t.recv(1.0), "ascii")
        tlm = decode(t.recv(1.0), "ascii")
        assert ack.type is MessageType.ACK and ack.seq == 7
        assert tlm.type is MessageType.TELEMETRY  # ping is answered with telemetry
        # a drive command just gets an ACK
        t.send(_drive(8))
        assert decode(t.recv(1.0), "ascii") == Message(MessageType.ACK, 8)
        t.close()
    finally:
        srv.stop()


def test_tcp_bad_frame_gets_nak() -> None:
    srv = _ResponderServer()
    try:
        t = TcpTransport("127.0.0.1", srv.port)
        t.open()
        t.send(b">5,drive,0.5,0.0*00\n")  # wrong CRC
        reply = decode(t.recv(1.0), "ascii")
        assert reply.type is MessageType.NAK and reply.reason == "crc"
        t.close()
    finally:
        srv.stop()


# ---- pty serial round-trip ----------------------------------------------


def test_roundtrip_over_pty_serial() -> None:
    master, slave = os.openpty()
    tty.setraw(master)
    tty.setraw(slave)
    slave_name = os.ttyname(slave)
    os.close(slave)  # let pyserial own the slave path; the responder uses the master

    stop = threading.Event()

    def responder_loop() -> None:
        responder = EchoResponder()
        while not stop.is_set():
            r, _, _ = select.select([master], [], [], 0.1)
            if master in r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                for out in responder.feed(data):
                    os.write(master, out)

    thread = threading.Thread(target=responder_loop, daemon=True)
    thread.start()
    try:
        t = SerialTransport(slave_name)
        t.open()
        t.send(_ping(3))
        ack = decode(t.recv(1.0), "ascii")
        tlm = decode(t.recv(1.0), "ascii")
        assert ack == Message(MessageType.ACK, 3)
        assert tlm.type is MessageType.TELEMETRY
        t.close()
    finally:
        stop.set()
        thread.join(timeout=1)
        os.close(master)


@pytest.mark.parametrize("encoding", ["ascii", "json"])
def test_responder_unit(encoding: str) -> None:
    r = EchoResponder(encoding=encoding)
    out = r.feed(encode(Message(MessageType.COMMAND, 1, "ping"), encoding))
    assert decode(out[0], encoding) == Message(MessageType.ACK, 1)
    assert decode(out[1], encoding).type is MessageType.TELEMETRY
