"""Provisioning & flashing — OS imaging, EEPROM/bootloader, clone, firmware.

Wraps the official Raspberry Pi tooling (``rpiboot``/``usbboot``, ``rpi-imager``,
``rpi-eeprom-*``) and ``arduino-cli``. Every destructive path is guarded by explicit
device safety checks and ``--confirm``/``--dry-run`` (see :mod:`pibot.provision.devices`).
"""

from __future__ import annotations
