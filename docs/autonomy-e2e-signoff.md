# Autonomy E2E sign-off (SPEC-2 M11 T11.6)

The acceptance bar that **cannot** be met without the physical robot + the fine-tuned policy:
the full autonomy journey — reflashed runtime → camera → remote VLA over Nebula → all three
prompted behaviors closed-loop → drop-to-stop → policy-link telemetry → power-loss survived.
This page is the checklist and the results record. It is the SPEC-2 analogue of the SPEC-1
[hardware-e2e-signoff.md](hardware-e2e-signoff.md).

> **Status: PENDING — not yet run on hardware.** The automated suite proves the *software*
> stack: the policy actuates **only** through the M4 safety gate (`tests/test_autonomy_safety.py`),
> a stalled policy drops to stop (`tests/test_autonomy_drop_to_stop.py`), and policy-link
> telemetry renders/alerts (`tests/test_telemetry.py`, `tests/test_monitor.py`). It does **not**
> certify this hardware journey. Per the repo's E2E rule, in-process proof is the standing
> proxy, not a substitute. Do not mark SPEC-2 M11 DoD met until the table below is filled on a
> real Pi + robot + a fine-tuned checkpoint.

## Preconditions

- **M7** runtime: the Pi reflashed + hardened ([runbooks/autonomy-runtime.md](runbooks/autonomy-runtime.md)),
  `pibot[ml]` installed, the obs→infer pipe proven.
- **M8** bring-up: camera + observation pipeline validated open-loop
  ([runbooks/autonomy-bringup.md](runbooks/autonomy-bringup.md)).
- **M10/M11** policy: a **fine-tuned** checkpoint covering all three tasks, served on the Mac's
  Nebula IP ([runbooks/finetune-and-serve.md](runbooks/finetune-and-serve.md)). Never closed-loop
  on a stock checkpoint (FR-18).
- Nebula overlay up ([runbooks/nebula-overlay.md](runbooks/nebula-overlay.md)); robot tethered or
  on blocks for first runs; e-stop in hand.

## Manual journey (record each result)

```bash
# 0. preview — prints the plan, opens no transport/camera/socket
pibot autonomy pibot --run --task goal --max-speed 0.2 --dry-run
# 1-3. each prompted behavior, closed-loop, lowest speed, e-stop in hand
pibot autonomy pibot --run --task goal     --max-speed 0.2   # "drive to the red ball"
pibot autonomy pibot --run --task follow   --max-speed 0.2   # "follow me"
pibot autonomy pibot --run --task explore  --max-speed 0.2   # "explore the room"
# 4. policy-link health while driving (T11.1) is LIVE in monitor (autonomy is in-process):
pibot monitor pibot --once          # policy connected=True infer …ms chunk_age …ms
# 5. drop-to-stop: stall the link mid-drive; the host deadman stops the robot within watchdog_ms
#    (inference is off-thread, so the agent's ticker keeps running), firmware watchdog backstops
# 6. power-loss: yank power mid-run; NVMe survives, the robot boots back to a safe stop
```

## Results

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 1 | drive-to-goal closed-loop | ⬜ pending | | |
| 2 | follow closed-loop | ⬜ pending | | |
| 3 | explore closed-loop | ⬜ pending | | |
| 4 | policy-link health LIVE in `monitor` | ⬜ pending | | fed by the in-process loop |
| 5 | hardware drop-to-stop on a stalled link | ⬜ pending | | host deadman ≤ watchdog_ms; firmware backstops |
| 6 | power-loss survived (NVMe + safe reboot) | ⬜ pending | | |
| 7 | no safety bypass observed across all runs | ⬜ pending | | |

## Architecture — autonomy runs in-process inside pibotd (decision resolved)

The earlier open question (standalone runner vs in-process) is **resolved: in-process.**
Closed-loop autonomy is an `AutonomyController` task *inside* pibotd, driving through the agent's
**single** `TransportController` + `AgentSafety` — the same gate teleop uses (`POST /autonomy`
starts it, `DELETE /autonomy` stops it; `pibot autonomy --run` is a thin client). Consequences,
all now proven in-process (`tests/test_autonomy_agent.py`, `tests/test_agent_endpoints.py`):

- **Policy-link telemetry is live.** The loop feeds the shared `PolicyLink` in `AgentState`, so
  `assemble_snapshot` carries the real block and `pibot monitor` shows `connected/infer/chunk_age`
  while driving — and flags `policy down` / stale chunk.
- **One transport, one safety gate.** No `/dev/ttyACM0` contention and no second `AgentSafety` —
  `agent/safety.py`'s "single place every command passes" invariant holds; a policy drive is
  clamped + e-stop-gated exactly like teleop.
- **Stall → host stop.** Inference runs in `asyncio.to_thread`, so a wedged policy never blocks
  the event loop; the controller's deadman ticker keeps running and stops the robot within
  `watchdog_ms`, with the firmware watchdog as the independent backstop (regression:
  `test_autonomy_agent.py::test_stalled_policy_still_drops_to_stop_via_the_agent_deadman`).

**Known trade-off (liveness).** In-process means the loop **outlives the client**: a hard
crash/kill of `pibot autonomy --run` leaves pibotd driving a *healthy* policy with nobody
watching (graceful `Ctrl-C` issues `DELETE /autonomy`; a SIGKILL does not). E-stop, the deadman,
and the firmware watchdog still backstop a *stalled* policy — not a healthy one. A client-liveness
heartbeat (tie the loop to the telemetry connection, or an autonomy keepalive) is a deliberate
follow-up, not yet built; until then halt out-of-band with `pibot estop` / `DELETE /autonomy`.

## Verify

The in-process proxies (software stack, no hardware) are the standing guarantee and must stay green:

```bash
.venv/bin/pytest tests/test_autonomy_safety.py tests/test_autonomy_drop_to_stop.py \
  tests/test_telemetry.py tests/test_monitor.py tests/e2e -q
```
