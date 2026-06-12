"""Pluggable transports carrying protocol frames between the Pi and the Arduino.

One :class:`~pibot.transport.base.Transport` interface, many backends: an in-memory
loopback (testing/dev), USB/UART serial, and TCP (Wi-Fi / ESP bridge). RFCOMM, BLE,
and I²C land in milestone M5. The agent (M4) is the sole owner of the active transport.
"""

from __future__ import annotations
