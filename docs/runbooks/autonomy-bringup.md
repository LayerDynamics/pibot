# Runbook — Autonomy open-loop bring-up (M8 T8.6)

The first time the VLA sees the real world: stream live camera + state observations to a
stock π₀.₅ on the M4 Max and **log the actions it returns — with the robot's motors never
moving**. This is the hard gate before any closed-loop motion (SPEC-2 FR-11): it validates
the observation schema, the image pipeline, and end-to-end latency on real data with zero
risk.

> **Status: PENDING — not yet run on hardware.** Needs the Pi (M7-reflashed) + a USB
> camera + the M4 Max serving a stock checkpoint. The software is built and gate-green
> (`pibot autonomy --open-loop`, `pibot.ml.openloop.OpenLoopEnvironment` — which holds no
> transport, so it *cannot* actuate).

## Prerequisites
- M7 done ([autonomy-runtime.md](autonomy-runtime.md)): hardened Pi, `pibot[ml]` installed,
  pipe proven.
- A USB UVC camera at `/dev/video0` (SPEC-2 OQ-3: model/mount).
- The M4 Max serving a **stock** `lerobot/pi05_base` over websocket :8000 ([PIML.md §6](../../PIML.md)).
- `~/.config/pibot/config.toml`: `policy_host` = the Mac's Nebula IP, `camera_device`,
  `action_horizon`, `control_hz`.

## 1. Run open-loop (logs actions, NO actuation)
```bash
pibot autonomy pibot --open-loop --prompt "drive to the red ball"
```

## 2. Watch the log
Each step logs `open-loop step: prompt=… action=…`. The motors stay still — the open-loop
environment has no transport to send to. Confirm the policy server accepts the observation
shape (no schema error) and note the round-trip latency on real data.

## Verify
```bash
# 1. camera produces 224x224 frames at >=15 fps (no schema rejection from the server)
pibot autonomy pibot --open-loop --prompt "follow me"
# 2. ZERO actuation — confirm no drive frames left the host while open-loop ran:
pibot monitor pibot --once        # transport idle; e-stop not needed; robot did not move
```

## Results
| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Camera ≥15 fps, obs assembly ≤50 ms | ⬜ pending | |
| 2 | Server accepts the obs schema | ⬜ pending | |
| 3 | End-to-end latency on real data | ⬜ pending | |
| 4 | **Zero actuation** (motors never moved) | ⬜ pending | |

---

# Closed-loop drive — first motion under the policy (M10 T10.6)

The first time the robot moves under the **fine-tuned** policy. Every action still passes the
M4 safety gate (clamp + latched e-stop + deadman) — proven in-process by
`tests/test_autonomy_safety.py` and `tests/test_autonomy_drop_to_stop.py` — but in-process
proof is not hardware proof. Run tethered, at the lowest clamps, with the e-stop **in your
hand**, and finish by physically stalling the link to confirm the robot stops (SPEC-2 §4.3, R-3).

> **Status: PENDING — not yet run on hardware.** Needs the fine-tuned checkpoint served
> ([finetune-and-serve.md](finetune-and-serve.md)) + the reflashed robot. Software gate-green
> (`pibot autonomy --run`, gated through `agent.safety.AgentSafety`).

## Prerequisites
- T10.5 done: a **fine-tuned** checkpoint served on the Mac's Nebula IP:8000. Never closed-loop
  on a stock checkpoint (FR-18, R-2).
- Robot tethered or on blocks first; clear floor; e-stop reachable.
- `config.toml`: `policy_host` = the Mac's Nebula IP, `transport`/`robot_host` = the ESP32 link.

## 1. Dry-run the plan (sends nothing)
Confirm the wiring — target, policy server, speed cap — before any motor can turn:
```bash
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2 --dry-run
```

## 2. Drive, lowest speed, e-stop in hand
The governor only ever lowers the clamp, never raises it — start at `--max-speed 0.2`:
```bash
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2
```
Watch for sane, smooth motion toward the goal. Hit the e-stop at the first surprise; a latched
e-stop drops every policy drive (regression-proven).

## 3. Hardware drop-to-stop
With the robot driving, **physically stall the link** (pull the Mac off Nebula / kill the
server / block WiFi). The control loop blocks waiting on the next inference, so on a **hard
stall it is the firmware watchdog** (independent, on the ESP32) that halts the motors — do
*not* expect a host `stop` frame in this case. The host deadman covers the other failure mode:
the loop alive but not feeding accepted commands (e.g. a malformed/empty chunk), where it emits
a `stop` within `watchdog_ms`. Either way the robot must come to rest — confirm it physically
halts.

## Verify
```bash
# 1. dry-run prints the plan and opens no transport/camera/socket
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2 --dry-run
# 2. after a real run, the e-stop latch + deadman behaviour is the SAME path the tests prove:
.venv/bin/pytest tests/test_autonomy_safety.py tests/test_autonomy_drop_to_stop.py -q
# 3. policy-link health while driving (T11.1) is LOGGED BY THE `pibot autonomy --run` PROCESS
#    (`autonomy step: policy={'connected': True, 'last_inference_ms': …, 'chunk_age_ms': …}`).
#    It does NOT yet appear in `pibot monitor` — feeding pibotd's /telemetry is a pending
#    integration (the runner is a separate process); see docs/autonomy-e2e-signoff.md.
# 4. hardware drop-to-stop: stall the link mid-drive and confirm the robot physically halts
#    (firmware watchdog is primary on a hard stall; the host deadman covers loop-alive-but-quiet)
pibot monitor pibot --once        # robot stationary after the stall
```

## Closed-loop results
| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Dry-run previews, actuates nothing | ⬜ pending | |
| 2 | ≥1 task completes closed-loop (tethered, low speed) | ⬜ pending | task: drive-to-red-ball |
| 3 | Latched e-stop blocks policy drive (on hardware) | ⬜ pending | |
| 4 | **Hardware drop-to-stop** on a stalled link | ⬜ pending | hard stall → firmware watchdog halts motors |
| 5 | No safety bypass observed | ⬜ pending | |
