# Runbook — Fine-tune π₀.₅ + serve the checkpoint (M10 T10.5)

Turn the M9 demonstrations into a policy the robot can actually run: LoRA-fine-tune
`lerobot/pi05_base` on the PiBot dataset, then serve that checkpoint from the M4 Max over the
Nebula overlay so the Pi's closed-loop client (`pibot autonomy --run`) can reach it. Never go
closed-loop on a stock checkpoint (SPEC-2 FR-18, R-2) — a zero-shot policy has no idea what
`drive(v, ω)` means for *this* robot.

> **Status: PENDING — not yet run on hardware.** Needs the M9 dataset + norm stats
> ([data-collection.md](data-collection.md)) and the M4 Max (or the swappable GPU host, OQ-7).
> The client/serving plumbing is built and gate-green (`pibot.ml.transforms`,
> `pibot.ml.norm_stats`, `pibot.ml.pipe_check`, `pibot autonomy --run`).

## Prerequisites
- M9 done: a LeRobot dataset per task + `norm_stats.json` (state/action = `[v, ω]`, dim 2).
- OQ-7 resolved — fine-tune host decided: M4 Max LoRA in-place **or** a rented GPU; either way
  the *serving* host is the Mac on the Nebula overlay (FR-14, swappable).
- `openpi` checked out on the host; the PiBot transforms registered as the `pibot` policy config
  (`PibotInputs`/`PibotOutputs`, `ACTION_DIM=2`) — see [PIML.md §5–6](../../PIML.md).
- Nebula up ([nebula-overlay.md](nebula-overlay.md)); the Mac's overlay IP is reachable from the Pi.

## 1. Fine-tune on the PiBot dataset
LoRA-fine-tune the base checkpoint on the combined demonstrations, using the PiBot norm stats
so inputs/outputs are normalized the same way at train and serve time:
```bash
# on the fine-tune host (OQ-7); MPS fallback covers any op gap (R-1)
PYTORCH_ENABLE_MPS_FALLBACK=1 \
  python scripts/train.py --config pibot \
    --dataset.repo_id pibot-drive-to-the-red-ball \
    --norm_stats demos/norm_stats.json \
    --output_dir checkpoints/pibot-pi05-lora
```

## 2. Serve the checkpoint on the Nebula IP
Bind the policy server to the Mac's **overlay** address (not the LAN), port 8000, so only the
robot on the mesh can reach it:
```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 \
  python scripts/serve_policy.py \
    --policy.config=pibot --policy.dir=checkpoints/pibot-pi05-lora \
    --host 192.168.100.10 --port 8000        # 192.168.100.10 = the Mac's Nebula IP
```

## 3. Round-trip the served checkpoint from the Pi
Before any motion, prove the Pi can reach the server and the shapes/latency are sane:
```bash
# on the Pi (overlay up); probes obs -> infer -> action chunk and prints timing
python -m tools.pipe_check --host 192.168.100.10 --port 8000 --rounds 20
```

## 4. Multi-task fine-tune — all three behaviors (M11 T11.4)
Once **follow** and **explore** demos are recorded ([data-collection.md](data-collection.md)),
re-fine-tune over the *combined* dataset so one checkpoint serves all three prompts, then drive
each prompt closed-loop:
```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 \
  python scripts/train.py --config pibot \
    --dataset.repo_id pibot-multitask \
    --norm_stats demos/norm_stats.json \
    --output_dir checkpoints/pibot-pi05-multitask
# serve it (step 2), then drive each behavior by prompt (M11 --task shorthand):
pibot autonomy pibot --run --task goal     --max-speed 0.2   # "drive to the red ball"
pibot autonomy pibot --run --task follow   --max-speed 0.2   # "follow me"
pibot autonomy pibot --run --task explore  --max-speed 0.2   # "explore the room"
```
Watch for **catastrophic forgetting** (R-1): if fine-tuning for three regresses one, keep a
per-task eval and, if needed, fall back to per-task checkpoints selected by prompt.

## Verify
```bash
# 1. the checkpoint exists and carries the PiBot norm stats
ls checkpoints/pibot-pi05-lora && grep -q '"action"' demos/norm_stats.json && echo "ckpt+stats OK"
# 2. the Pi round-trips the SERVED checkpoint: action dim == 2 ([v, ω]) and p50 within budget
python -m tools.pipe_check --host 192.168.100.10 --port 8000 --rounds 20
# expect: action shape (..., 2); server_timing infer p50 well under the control period (1/control_hz)
```

## Results
| # | Check | Target | Status | Notes |
|---|-------|--------|--------|-------|
| 1 | Fine-tune completes | loss converged, ckpt saved | ⬜ pending | host (OQ-7): — |
| 2 | Server serves on the Nebula IP | reachable :8000 from the Pi | ⬜ pending | |
| 3 | `pipe_check` round-trips | action dim = 2 | ⬜ pending | |
| 4 | Inference p50 within budget | < control period (1/`control_hz`) | ⬜ pending | measured: — ms |
| 5 | Multi-task fine-tune (T11.4) | one ckpt serves all three | ⬜ pending | host (OQ-7): — |
| 6 | Each prompt drives its behavior | goal / follow / explore | ⬜ pending | per-task eval: — |
