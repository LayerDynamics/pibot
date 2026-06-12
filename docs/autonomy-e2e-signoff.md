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
# 4. policy-link health while driving (T11.1): LOGGED BY the `pibot autonomy --run` process
#    (`autonomy step: policy={'connected': True, 'last_inference_ms': …}`). It does NOT yet
#    reach `pibot monitor` — see the open decision below.
# 5. drop-to-stop: stall the link mid-drive; firmware watchdog halts the motors
# 6. power-loss: yank power mid-run; NVMe survives, the robot boots back to a safe stop
```

## Results

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 1 | drive-to-goal closed-loop | ⬜ pending | | |
| 2 | follow closed-loop | ⬜ pending | | |
| 3 | explore closed-loop | ⬜ pending | | |
| 4 | policy-link health logged by the runner | ⬜ pending | | `monitor` feed: pending integration (below) |
| 5 | hardware drop-to-stop on a stalled link | ⬜ pending | | firmware watchdog primary |
| 6 | power-loss survived (NVMe + safe reboot) | ⬜ pending | | |
| 7 | no safety bypass observed across all runs | ⬜ pending | | |

## Open decision — autonomy process model (affects steps 4 & 5)

`run_closed_loop` today builds its **own** transport + its **own** `AgentSafety` (a *standalone*
process). Two consequences this sign-off must not paper over:

- **Policy-link telemetry feed.** `agent/telemetry.py`'s `PolicyLink` schema/render/threshold/CSV
  are done and unit-proven (T11.1), but nothing feeds the live block into the snapshot pibotd
  serves — `assemble_snapshot` is called once (`agent/app.py`) with no `policy` arg, so
  `pibot monitor` always shows `connected=None`. Live policy health is only in the runner's logs.
- **Concurrency with pibotd.** Running `pibot autonomy --run` and `pibot monitor` at once needs
  pibotd live *beside* the runner. On a **serial** ESP32 link `/dev/ttyACM0` is exclusive — both
  can't open it — and two `AgentSafety` gates on two connections violates `agent/safety.py`'s
  stated invariant ("the single place every command passes before the transport").

**Resolution path (post-SPEC-2):** run closed-loop autonomy *in-process inside pibotd* — one
transport, one `AgentSafety`, and feeding the telemetry `PolicyLink` becomes trivial — or keep it
standalone and accept that `monitor` does not show policy health during a run. Decide before
relying on step 4 via `monitor`; until then, treat the runner's logs as the source of truth.

## Verify

The in-process proxies (software stack, no hardware) are the standing guarantee and must stay green:

```bash
.venv/bin/pytest tests/test_autonomy_safety.py tests/test_autonomy_drop_to_stop.py \
  tests/test_telemetry.py tests/test_monitor.py tests/e2e -q
```
