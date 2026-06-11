# Runbook — Wireless (and wired-bus) transport bring-up

Bring the robot link up over each supported transport. The default and simplest is
**Wi-Fi/TCP to an ESP32** running the firmware; BLE, RFCOMM, I²C, and GPIO-UART are also
supported. Every transport fails safe: a dropped link marks it down so the deadman watchdog
(and the firmware backstop) stop the robot — see [e-stop.md](e-stop.md).

## Wi-Fi / TCP (ESP32 — the default wireless controller)

```bash
# Flash the ESP32 controller, then read the IP it prints over serial.
pibot firmware flash firmware/pibot_esp32 --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0 --dry-run
pibot firmware flash firmware/pibot_esp32 --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0
```

Then point the agent's transport at it (`~/.config/pibot/config.toml`):

```toml
transport = "tcp"
robot_host = "192.168.1.50"   # the ESP32's IP
tcp_port = 3333
```

## BLE (Nordic-UART style)

```toml
transport = "ble"
ble_address = "AA:BB:CC:DD:EE:FF"   # the peripheral's BLE address
```

Install the BLE dependency on the Pi: `pip install 'pibot[ble]'` (bleak).

## RFCOMM (Bluetooth Classic)

```bash
# bind the device to /dev/rfcomm0 on the Pi first
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
```

```toml
transport = "rfcomm"
rfcomm_address = "AA:BB:CC:DD:EE:FF"
```

## I²C and GPIO-UART (wired)

These need a 3.3 V ↔ 5 V level shifter for 5 V microcontrollers — see the wiring notes in
[../../firmware/README.md](../../firmware/README.md).

```toml
# I2C
transport = "i2c"
i2c_bus = 1
i2c_address = 0x08
# or GPIO-UART (requires enable_uart=1 in /boot/firmware/config.txt)
# transport = "uart"
```

Install the I²C dependency on the Pi: `pip install 'pibot[i2c]'` (smbus2).

## Verify

With the agent running over the chosen transport, a `ping` should round-trip and telemetry
should flow:

```bash
pibot agent start pibot
pibot cmd pibot ping            # expected: ping -> ACK
pibot monitor pibot --once      # transport shows open=True with the selected backend
```
