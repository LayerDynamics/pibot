"""T3.4 — TcpTransport against a loopback TCP echo server (no hardware).

Covers the framing contract, reassembly across TCP segment boundaries, and — most
importantly for a wireless motion path — the fail-safe when the server drops the
connection (is_open -> False, recv -> None).
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest
from helpers import assert_transport_contract

from pibot.transport.tcp import TcpTransport


class _EchoServer:
    def __init__(self, *, per_byte: bool = False) -> None:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._per_byte = per_byte
        self._conns: list[socket.socket] = []
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._srv.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except (TimeoutError, OSError):
                continue
            self._conns.append(conn)
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            while not self._stop:
                data = conn.recv(4096)
                if not data:
                    break
                if self._per_byte:
                    for b in data:
                        conn.sendall(bytes([b]))
                        time.sleep(0.001)
                else:
                    conn.sendall(data)
        except OSError:
            pass

    def drop_clients(self) -> None:
        for c in self._conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()
        self._conns = []

    def stop(self) -> None:
        self._stop = True
        self.drop_clients()
        self._srv.close()


@pytest.fixture
def echo() -> Iterator[_EchoServer]:
    srv = _EchoServer()
    try:
        yield srv
    finally:
        srv.stop()


def test_tcp_satisfies_contract(echo: _EchoServer) -> None:
    assert_transport_contract(lambda: TcpTransport("127.0.0.1", echo.port))


def test_two_frames_in_order(echo: _EchoServer) -> None:
    t = TcpTransport("127.0.0.1", echo.port)
    t.open()
    t.send(b">1,ping*5B\n")
    t.send(b">2,stop*1A\n")
    assert t.recv(0.5) == b">1,ping*5B\n"
    assert t.recv(0.5) == b">2,stop*1A\n"
    t.close()


def test_reassembles_across_tcp_segments() -> None:
    srv = _EchoServer(per_byte=True)  # echoes one byte at a time -> forces reassembly
    try:
        t = TcpTransport("127.0.0.1", srv.port)
        t.open()
        t.send(b">1,drive,0.5,0.0*7C\n")
        assert t.recv(1.0) == b">1,drive,0.5,0.0*7C\n"
        t.close()
    finally:
        srv.stop()


def test_server_drop_is_failsafe(echo: _EchoServer) -> None:
    t = TcpTransport("127.0.0.1", echo.port)
    t.open()
    t.send(b">1,ping*5B\n")
    assert t.recv(0.5) == b">1,ping*5B\n"  # drain the echo
    echo.drop_clients()
    assert t.recv(0.5) is None  # peer gone -> no frame
    assert t.is_open is False  # and the transport reports it down (watchdog will e-stop)


def test_reconnect_to_fresh_server(echo: _EchoServer) -> None:
    t = TcpTransport("127.0.0.1", echo.port)
    t.open()
    assert t.is_open
    t.close()
    assert t.is_open is False
    t.open()
    t.send(b">9,ping*5B\n")
    assert t.recv(0.5) == b">9,ping*5B\n"
    t.close()


def test_info(echo: _EchoServer) -> None:
    t = TcpTransport("127.0.0.1", echo.port)
    t.open()
    info = t.info
    assert info["backend"] == "tcp"
    assert info["port"] == echo.port
    assert info["open"] is True
    t.close()
