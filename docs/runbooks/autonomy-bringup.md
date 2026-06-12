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

Autonomy runs **in-process inside pibotd** (like teleop): the agent owns the camera, the policy
client, the transport, and the single safety gate; `pibot autonomy --run` is a thin client that
tells the agent to start driving and streams policy-link health back.

## Prerequisites
- T10.5 done: a **fine-tuned** checkpoint served on the Mac's Nebula IP:8000. Never closed-loop
  on a stock checkpoint (FR-18, R-2).
- Robot tethered or on blocks first; clear floor; e-stop reachable.
- **pibotd running on the Pi**, its config set: `policy_host` = the Mac's Nebula IP,
  `camera_device`, `transport`/`robot_host` = the ESP32 link. The CLI reaches the agent only.

## 1. Dry-run the plan (sends nothing)
Confirm the wiring — target, speed cap, prompt — before any motor can turn:
```bash
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2 --dry-run
```

## 2. Drive, lowest speed, e-stop in hand
The governor only ever lowers the clamp, never raises it — start at `--max-speed 0.2`. The agent
drives until you `Ctrl-C` (which tells it to stop):
```bash
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2
```
Watch for sane, smooth motion toward the goal. Hit the e-stop at the first surprise; a latched
e-stop drops every policy drive (regression-proven — the policy submits through the *same* gate
as teleop).

> **Liveness caveat:** autonomy runs *inside pibotd*, so it outlives the client. A graceful
> `Ctrl-C` tells the agent to stop, but a **hard crash/kill of the CLI leaves pibotd driving** a
> healthy policy with nobody watching. To halt out-of-band: `pibot estop pibot` or
> `curl -X DELETE …/autonomy`. The deadman + firmware watchdog still backstop a *stalled* policy,
> but not a *healthy* one — keep the e-stop in hand.

## 3. Hardware drop-to-stop
With the robot driving, **physically stall the link** (pull the Mac off Nebula / kill the
server / block WiFi). Inference runs **off the control thread** (`asyncio.to_thread`), so a
stalled policy does *not* block the agent: its deadman ticker keeps running and emits a `stop`
within `watchdog_ms` of the last accepted command. The **firmware watchdog** on the ESP32 is
the independent backstop. Confirm the robot comes to rest.

## Verify
```bash
# 1. dry-run prints the plan and contacts the agent not at all
pibot autonomy pibot --run --prompt "drive to the red ball" --max-speed 0.2 --dry-run
# 2. the policy drives through the SAME safety gate as teleop — proven in-process:
.venv/bin/pytest tests/test_autonomy_agent.py tests/test_agent_endpoints.py \
  tests/test_autonomy_safety.py tests/test_autonomy_drop_to_stop.py -q
# 3. policy-link health is LIVE in monitor while driving (T11.1, fed by the in-process loop):
pibot monitor pibot --once        # `policy connected=True infer …ms chunk_age …ms`
# 4. hardware drop-to-stop: stall the link mid-drive; the host deadman stops the robot within
#    watchdog_ms (firmware watchdog backstops). Confirm it physically halts.
pibot monitor pibot --once        # robot stationary; policy goes connected=False / chunk stale
```

## Closed-loop results
| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | Dry-run previews, actuates nothing | ⬜ pending | |
| 2 | ≥1 task completes closed-loop (tethered, low speed) | ⬜ pending | task: drive-to-red-ball |
| 3 | Latched e-stop blocks policy drive (on hardware) | ⬜ pending | |
| 4 | **Hardware drop-to-stop** on a stalled link | ⬜ pending | hard stall → firmware watchdog halts motors |
| 5 | No safety bypass observed | ⬜ pending | |
