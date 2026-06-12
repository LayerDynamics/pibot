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
