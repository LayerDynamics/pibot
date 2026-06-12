# Plan — M10: Fine-tune & Closed Loop (Safety-Gated)

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

| | |
|---|---|
| **Spec** | [SPEC-2](../specs/SPEC-2-pibot-autonomy-platform.md) §3.8, §4.1 Phase D, FR-4/5/6/12/18, §5 M10 |
| **Milestone** | M10 |
| **Depends on** | M9 (transforms + dataset) |
| **Branch** | `m10-finetune-closed-loop` |
| **Date** | 2026-06-11 |
| **Status** | Not started (planned — no code yet) |

**Goal:** The robot **drives itself** on ≥1 prompted task from a fine-tuned π₀.₅ — every action through the M4 safety gate, with verified drop-to-stop.
**Architecture:** `apply_action` → `_action_to_command` → **M4 safety gate** → M3 transport; a fine-tuned checkpoint served from the M4 Max; the policy is provably *behind* safety and stops on stall.
**Practices:** TDD + typed-first; SPEC-1 gates; the safety-bypass + drop-to-stop tests are the headline; the fine-tune + on-robot drive are gated HIL procedures.

## Goal
Close the loop safely: a fine-tuned policy actuates the real robot, and the VLA can never bypass clamp/e-stop/deadman.

## In scope
The closed-loop `apply_action` path; the action→command mapper; the safety-bypass + drop-to-stop regressions; `pibot autonomy run` (closed-loop) with first-run clamp flags; the HIL fine-tune + tethered drive.

## Out of scope
Multi-task breadth + ops/observability polish (M11).

## Prerequisites
- M9 done (dataset + transforms + norm stats).
- OQ-7 resolved (fine-tune host: M4 Max LoRA vs rented GPU) before T10.5.

## Tasks

### T10.1 — Closed-loop `apply_action` (action → safety → transport)
- **Files:** `pibot/ml/pibot_environment.py` (`apply_action`, `_action_to_command`); `tests/test_pibot_environment.py`
- **Test first:** a policy action vector → `_action_to_command` produces the expected `drive(v,ω)` frame; `apply_action` submits it **through the M4 safety gate** (use a fake safety + responder transport) and the clamped frame reaches the transport; servo columns map to `servo(id,deg)`.
- **Implement:** the real `apply_action` (replaces the M8 `NotImplementedError` stub) routing through `AgentSafety.submit`.
- **Done when:** mapping + gated-send tests green.

### T10.2 — Safety-bypass regression (the policy CANNOT bypass safety)
- **Files:** `tests/test_autonomy_safety.py`
- **Test first:** (a) a latched e-stop makes `apply_action` a no-op / rejected exactly like a teleop motion (no frame sent); (b) an over-range action is **clamped** identically to a teleop command; (c) the policy path and the teleop path produce the same safety verdict for the same command.
- **Implement:** none beyond T10.1 (assertions over the existing path).
- **Done when:** bypass regressions green (FR-4/FR-19 proven).

### T10.3 — Drop-to-stop with the policy in the loop
- **Files:** `tests/e2e/test_autonomy_drop_to_stop.py`
- **Test first:** in-process E2E (mirrors M4): Runtime + a fake policy that **stalls** (stops returning chunks) → the deadman emits a `stop` frame within the window; assert a stop reached the transport. Proves a dropped policy stream halts the robot (FR-5, §3.8).
- **Implement:** none beyond wiring the test harness.
- **Done when:** drop-to-stop E2E green.

### T10.4 — `pibot autonomy run` (closed-loop) CLI
- **Files:** `pibot/cli.py` (`autonomy run`); `tests/test_cli_autonomy.py`
- **Test first:** `pibot autonomy run <target> --prompt "drive to the red ball" --max-speed 0.3` dispatches to the closed-loop runner with reduced clamp limits for first runs; STATE_CHANGING → supports `--dry-run` (prints the plan, sends nothing); consistency test updated.
- **Implement:** subcommand + handler; `--dry-run` previews the prompt/host/limits.
- **Done when:** dispatch + `--dry-run` + consistency tests green.

### T10.5 — (HIL) Fine-tune + serve
- **Files:** `docs/runbooks/finetune-and-serve.md` (procedure + checkpoint manifest)
- **Procedure:** fine-tune π₀.₅ on the M9 dataset (host per OQ-7) using the PiBot config + norm stats; serve the checkpoint via `scripts/serve_policy.py --policy.config=pibot --policy.dir=<ckpt>` (PyTorch-MPS) bound to the Mac's Nebula IP:8000.
- **Done when:** fine-tuned checkpoint served; `pipe_check` round-trips it; server `server_timing` within budget.

### T10.6 — (HIL) Closed-loop drive, ≥1 task
- **Files:** `docs/runbooks/autonomy-bringup.md` (append closed-loop results)
- **Procedure:** robot tethered/low-speed, e-stop in hand, reduced clamps; `pibot autonomy run --prompt "drive to the red ball"`; verify the behavior, then **physically stall the link** and confirm drop-to-stop on hardware.
- **Done when:** ≥1 task completes closed-loop; hardware drop-to-stop verified; no safety bypass observed.

## Milestone acceptance criteria (SPEC-2 M10)
Fine-tuned checkpoint served; ≥1 task closed-loop on the robot; drop-to-stop + safety-bypass tests pass (in-process) and drop-to-stop verified on hardware.

## Risks
- **Zero-shot/under-fit policy** (R-2) → never closed-loop on a stock ckpt (FR-18); if behavior is poor, collect more demos (back to M9) — do not loosen safety to compensate.
- **MPS op gap on the fine-tuned forward** (R-1) → `PYTORCH_ENABLE_MPS_FALLBACK=1`; escalate to the swappable GPU host (FR-14).
- **First closed-loop run unsafe** → tether + lowest clamps + e-stop in hand (rollout strategy §4.3).

## Definition of done
Software gates green; safety-bypass + drop-to-stop proven in-process; HIL fine-tune + tethered drive recorded with hardware drop-to-stop; branch ready to commit (ask first).
