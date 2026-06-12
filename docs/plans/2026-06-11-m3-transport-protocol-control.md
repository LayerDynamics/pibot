# Plan — M3: Transport, Protocol & Control (serial + TCP)

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-4, §6.3–6.5 |
| **Milestone** | M3 |
| **Depends on** | M1 |
| **Branch** | `m3-transport-protocol-control` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Shipped (commit `1505d85`) |

> Conventions per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).
> **Refinement of SPEC-1 §8:** per the planning decision, the **TCP/Wi-Fi transport is
> built here (M3) alongside serial**, not deferred to M5, so wireless teleop is
> reachable by M4. RFCOMM/BLE/I²C/UART remain M5.

## Goal
Establish how the Pi talks to the Arduino: a robust, fully-tested wire **protocol
codec**, a pluggable **`Transport`** abstraction with **serial and TCP** backends, a
reference **Arduino firmware** (with an echo/test mode and an ESP32 TCP variant), and
the one-shot `cmd`/`estop` commands with their safety primitives.

## In scope
`protocol.py` codec, `Transport` ABC, `SerialTransport`, `TcpTransport`, reference
firmware (`pibot_arduino`), `pibot cmd`, `pibot estop`, shared safety primitives
(clamp, e-stop signal, frame-level seq/ack).

## Out of scope
The long-running agent, teleop loop, telemetry dashboards (M4); RFCOMM/BLE/I²C/UART
(M5).

## Prerequisites
- M1 (so `firmware flash`/SSH paths exist for Pi-wired Arduinos).
- `arduino-cli` present (verified) for compile-checking the sketch in CI.

## Tasks

### T3.1 — Protocol codec (pure, exhaustively TDD — highest-value tests)
- **Files:** `pibot/protocol/codec.py` (shared; symlinked/imported by agent in M4)
- **Test first:** `tests/test_protocol.py` —
  - **Compact framed ASCII:** encode `drive(v,w)`/`servo`/`stop`/`ping`/`set` →
    `>SEQ,CMD,ARGS*CRC8\n`; decode telemetry `<SEQ,TYPE,FIELDS*CRC8\n`; `ACK SEQ`/`NAK
    SEQ REASON`.
  - **CRC8:** known-vector checks; corrupted byte → decode rejects (NAK reason `crc`).
  - **Sequence:** monotonic wrap at 8-bit; duplicate-seq detection; out-of-order flag.
  - **JSON-lines variant:** `{"seq":N,"cmd":"drive","v":..,"w":..}` round-trips to the
    same logical message; both encodings decode to one `Message` type.
  - **Fuzz:** random byte streams never crash the decoder (property test).
- **Implement:** `encode(msg, encoding)`, `decode(frame) -> Message | Nak`, CRC8,
  seq tracker, both encodings behind one `Message` dataclass set.
- **Done when:** 100 % branch coverage on the codec; fuzz test green.

### T3.2 — `Transport` ABC + contract test
- **Files:** `pibot/transport/base.py`, `tests/test_transport_contract.py`
- **Test first:** a reusable contract suite (`open/close/send/recv/is_open/info`)
  that any backend must satisfy, run against an in-memory `LoopbackTransport` fake.
- **Implement:** `Transport` ABC + `LoopbackTransport` (test util) + the contract test
  harness.
- **Done when:** contract suite green against the loopback.

### T3.3 — `SerialTransport` (USB / GPIO-UART / RFCOMM-compatible)
- **Files:** `pibot/transport/serial.py`
- **Test first:** `tests/test_transport_serial.py` — drive it over a **pty loopback**
  (`os.openpty`) so a real serial peer is simulated without hardware: frames written
  one end decode at the other; partial reads reassemble to whole frames; timeout →
  `recv` returns `None`; reconnect after close.
- **Implement:** `pyserial`-based backend with frame reassembly buffer; works for
  `/dev/ttyACM*`, `/dev/serial0`, and later `/dev/rfcomm*` (same code path).
- **Done when:** pty-loopback contract + reassembly + timeout tests green.

### T3.4 — `TcpTransport` (Wi-Fi / ESP bridge) — promoted into M3
- **Files:** `pibot/transport/tcp.py`
- **Test first:** `tests/test_transport_tcp.py` — against a **loopback TCP echo
  server** (spun up in the test): connect, send/recv framed messages, partial-segment
  reassembly, server-drop → `is_open` False + `recv` None (fail-safe signal), reconnect.
- **Implement:** TCP socket backend with the same framing/reassembly as serial; health
  via `last_frame_ms`.
- **Done when:** loopback-TCP contract + drop/reconnect tests green.

### T3.5 — Reference Arduino firmware + echo stand
- **Files:** `firmware/pibot_arduino/pibot_arduino.ino`,
  `firmware/pibot_arduino/protocol.h/.cpp`, `firmware/esp32_tcp_bridge/…`,
  `tests/stands/echo_firmware/` (host-side harness)
- **Test first:** `tests/test_echo_roundtrip.py` — the host codec sends `ping`/`drive`
  over a pty (serial) and a TCP loopback (esp32 variant emulator) to an **echo
  responder** that mirrors the firmware parser, asserting ACK + synthetic telemetry;
  `tests/test_firmware_compiles.py` runs `arduino-cli compile` for the AVR sketch and
  the ESP32 bridge (skipped if cores missing, but wired for CI).
- **Implement:** the AVR sketch (command parser mirroring `codec.py`, independent
  hardware watchdog, motor/servo dispatch hooks, telemetry emit, **echo/test mode**),
  an ESP32 TCP bridge variant, and the host-side echo responder used as the CI stand.
- **Done when:** codec↔firmware round-trip green over both serial and TCP loopback;
  compile job wired.

### T3.6 — Safety primitives (shared)
- **Files:** `pibot/control/safety.py`
- **Test first:** `tests/test_safety.py` — `clamp(cmd, limits)` bounds velocity/servo
  to configured maxima; `EStop` latches and rejects motion until explicit `resume`;
  a frame-level watchdog timer (injected clock) trips after `deadman_ms`.
- **Implement:** clamp, latched e-stop, watchdog primitive (reused by the agent in M4
  and mirrored by firmware).
- **Done when:** clamp/e-stop/watchdog branches covered with a fake clock.

### T3.7 — `pibot cmd` and `pibot estop`
- **Files:** `pibot/control/oneshot.py`, CLI wiring
- **Test first:** `tests/test_cmd.py` — `pibot cmd <t> ping` opens the configured
  transport, sends, awaits ACK (timeout → error), `--json` result; `pibot cmd <t>
  drive 0.5 0.0` clamps then sends; `pibot estop <t>` sends the highest-priority stop;
  refuses motion while e-stop latched.
- **Implement:** one-shot command path (direct transport when no agent running; via
  agent in M4) using codec + safety.
- **Done when:** unit tests green over the loopback transports.

## Milestone acceptance criteria (SPEC-1 §8 M3, refined)
- Codec unit tests (encode/decode/CRC/seq/JSON/fuzz) pass at full branch coverage.
- `pibot cmd <pi> ping` round-trips an ACK through the Arduino over **serial and TCP**
  (echo stand in CI; real Arduino in HIL).
- E-stop halts a driven motor (HIL on hardware).
- All gates green.

## Risks
- **Codec bugs corrupting motion commands** → exhaustive + fuzz tests; CRC + seq;
  firmware NAKs bad frames.
- **Pi 3.3 V ↔ Arduino 5 V on UART** (relevant once UART used in M5) → flagged now;
  default serial(USB) is 5 V-safe; firmware README documents the level shifter.
- **TCP/Wi-Fi as a motion path** → safety watchdog + firmware backstop mandatory;
  wireless drop test (T3.4) asserts fail-safe.

## Definition of done
All gates pass; acceptance met; codec at full coverage; serial **and** TCP round-trip
the echo stand; safety primitives proven; branch ready to commit (ask first).
