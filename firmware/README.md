# PiBot Firmware

Reference firmware for the PiBot "muscles" layer. **Wireless-first: the ESP32 is the
primary controller** — one board joins Wi-Fi, drives the motors/servos directly, and
serves the PiBot protocol over TCP, so the Pi talks to it over Wi-Fi / the ZeroTier
overlay with no USB cable and no separate Arduino. All sketches speak the same wire
protocol as the host codec (`pibot/protocol/codec.py` / `protocol.h`); the host-side
mirror used for no-hardware tests is `pibot/control/echo.py`.

## Sketches

| Sketch | Board | Role |
|---|---|---|
| **`pibot_esp32/`** | **ESP32** (WROOM/S3/C3) | **PRIMARY — Wi-Fi controller**: drives motors/servos AND serves the protocol on TCP :3333. Verified: compiles to 70 % flash. |
| `pibot_arduino/` | Arduino Uno/Nano/Mega (AVR) | Wired alternative — same firmware over USB serial (5 V, no Wi-Fi). Verified: 29 % flash on an Uno. |
| `esp32_tcp_bridge/` | ESP32 | Only if you already have an AVR motor controller: dumb Wi-Fi↔serial bridge to it. |

The default robot is **an ESP32 + a dual H-bridge motor driver** — fully wireless.

## Safety (mirrors `pibot/control/safety.py`)

1. **Clamp** — `drive`/`servo`/`motor` values bounded before actuation.
2. **E-stop** — `estop` latches; motion refused (NAK `estop`) until `set,estop,0`.
3. **Watchdog** — no valid command within `WATCHDOG_MS` (300 ms) → motors stop.
4. **Link-loss (ESP32)** — the TCP client disconnecting → motors stop *immediately*. A
   dropped Wi-Fi link must never leave the robot driving.

Guards 3–4 are **independent of the Pi**: a frozen brain or dead link still halts.

## Wiring — `pibot_esp32` (set in the CONFIG block)

- Dual H-bridge (TB6612/L298-style): left PWM/DIR on GPIO `25`/`26`, right on `32`/`33`.
- Servos on GPIO `18`/`19` (LEDC 50 Hz).
- Battery divider on GPIO `34` (ADC1); set `VBAT_SCALE` for your divider.
- Set `WIFI_SSID` / `WIFI_PASS`.

PWM and servos use the ESP32 **LEDC** peripheral (Arduino-ESP32 core **3.x** API). The
ESP32 is 3.3 V — match your motor driver's logic level (TB6612/L298 accept 3.3 V logic).

## Build / flash

```bash
# ESP32 (install the official core first: arduino-cli core install esp32:esp32)
pibot firmware build firmware/pibot_esp32 --fqbn esp32:esp32:esp32
pibot firmware flash firmware/pibot_esp32 --fqbn esp32:esp32:esp32 --port /dev/ttyUSB0

# AVR alternative
pibot firmware build firmware/pibot_arduino --fqbn arduino:avr:uno
```

Once flashed and on Wi-Fi, the ESP32 prints its IP; the Pi connects with
`TcpTransport(<esp32-ip>, 3333)`.
