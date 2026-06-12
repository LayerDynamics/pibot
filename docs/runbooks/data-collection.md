# Runbook — Demonstration data collection (M9 T9.6)

Teleop-drive the robot through each task while recording `(observation, action)` pairs,
then convert them to a LeRobot dataset and compute normalization stats — the demonstrations
the policy is fine-tuned on (M10). The robot moves under **your** control (teleop); the VLA
is not in the loop here.

> **Status: PENDING — not yet run on hardware.** Needs the M7-reflashed Pi + a USB camera +
> a teleoperable robot. The software is built and gate-green (`pibot autonomy --record`,
> `pibot.ml.record`, `pibot.ml.dataset`, `pibot.ml.norm_stats`).

## Prerequisites
- M8 done ([autonomy-bringup.md](autonomy-bringup.md)): camera + obs pipeline validated.
- A teleoperable robot (motor driver wired to the ESP32).
- SPEC-2 OQ-4: how many demonstrations per task (start generous; M10 reveals if more needed).

## 1. Record per task
Record several runs for each of the three tasks (drive the robot well — the policy imitates
you):
```bash
pibot autonomy pibot --record --prompt "drive to the red ball" --out demos/goal
pibot autonomy pibot --record --prompt "follow me"            --out demos/follow
pibot autonomy pibot --record --prompt "explore the room"     --out demos/explore
```
Each session is teleop (WASD/arrows; `q` ends the episode); every step logs the camera
frame + the `[v, ω]` you commanded.

## 2. Build the dataset + norm stats
The record command writes a LeRobot dataset per `--out`. Compute normalization stats over
the combined dataset (used by the server's PibotInputs/Outputs):
```bash
python -c "from pibot.ml import norm_stats; ..."   # over the collected frames -> norm_stats.json
```

## Verify
```bash
# the datasets exist with per-task episodes and frames
ls -R demos/
# norm stats have the right shape ([v,w] = 2 dims for both state and action)
python -c "from pibot.ml import norm_stats; s=norm_stats.load('demos/norm_stats.json'); print(len(s['action']['mean']))"
```

## Results
| Task | Episodes | Frames | Status |
|------|----------|--------|--------|
| drive-to-goal | — | — | ⬜ pending |
| follow | — | — | ⬜ pending |
| explore | — | — | ⬜ pending |
| norm stats computed | | | ⬜ pending |
