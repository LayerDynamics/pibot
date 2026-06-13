# Plan — M9: Server Transforms & Demonstration Data

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

| | |
|---|---|
| **Spec** | [SPEC-2](../specs/SPEC-2-pibot-autonomy-platform.md) §3.2 (transforms, logger), §4.1 Phase C, FR-10, §5 M9 |
| **Milestone** | M9 |
| **Depends on** | M8 (camera + obs pipeline) |
| **Branch** | `m9-transforms-and-data` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Software shipped + committed (T9.1–T9.5; gate-green). HIL pending hardware — T9.6 (record demonstrations + build dataset). |

**Goal:** The server-side PiBot policy config (`PibotInputs`/`PibotOutputs` + norm stats) and a **LeRobot demonstration dataset** recorded via teleop for the three tasks — everything fine-tuning needs.
**Architecture:** A `Runtime` subscriber logs `(obs, action, ts)`; a converter writes the LeRobot dataset; server transforms map PiBot obs/actions ↔ the model (UR5 template); `compute_norm_stats` over the dataset.
**Practices:** TDD + contract-first + typed-first; SPEC-1 gates; the live demonstration recording is a gated HIL procedure.

## Goal
Produce the data + server config that turn a stock model into a PiBot-shaped one — still **no closed-loop motion**.

## In scope
Episode logger; LeRobot dataset writer; `server/pibot_policy.py` (`PibotInputs`/`PibotOutputs`); norm-stats wiring; `pibot autonomy record` (teleop demo capture); the HIL recording run.

## Out of scope
The fine-tune itself + closed-loop (M10). Multi-task coverage breadth (M11).

## Prerequisites
- M8 done (obs pipeline; open-loop validated).
- SPEC-2 OQ-2 resolved (`state_dim`/`action_dim` mapping) before T9.3.

## Tasks

### T9.1 — Episode logger (Runtime subscriber)
- **Files:** `pibot/ml/episode_logger.py`; `tests/test_episode_logger.py`
- **Test first:** `EpisodeLogger.on_step(obs, action)` appends a typed record `(obs, action, ts)`; `start_episode(prompt)`/`end_episode()` bound episodes; injected clock for deterministic timestamps; records are retrievable in order.
- **Implement:** subscriber matching openpi's `subscriber` interface; in-memory buffer + flush hook.
- **Done when:** logger tests green.

### T9.2 — LeRobot dataset writer
- **Files:** `pibot/ml/dataset.py`; `tests/test_dataset.py`
- **Test first:** given recorded episodes, the writer produces LeRobot-format rows (observation.image, observation.state, action, episode_index, frame_index, timestamp) — assert the column schema + per-episode indexing on a 2-episode fixture.
- **Implement:** converter modeled on openpi `examples/*/convert_*_to_lerobot.py`; write to a dataset dir.
- **Done when:** dataset-schema tests green.

### T9.3 — Server transforms `PibotInputs` / `PibotOutputs` (contract-first)
- **Files:** `server/pibot_policy.py`; `server/tests/test_pibot_policy.py`
- **Test first:** `PibotInputs(obs)` packs PiBot `{image,state,prompt}` into the model's expected dict (assert keys/shapes); `PibotOutputs(model_action)` slices columns → `[v, ω, servo…]` of length `action_dim` (OQ-2); a full `obs → PibotInputs → (identity) → PibotOutputs` round-trips shapes without error.
- **Implement:** transforms following `examples/ur5/README.md` + `src/openpi/policies/libero_policy.py`.
- **Done when:** transform shape tests green.

### T9.4 — Norm-stats wiring
- **Files:** `server/norm_stats.py`; `server/tests/test_norm_stats.py`
- **Test first:** over a tiny synthetic dataset, computed mean/std for state+action have the right shape and sane values; persisted + reloaded round-trips.
- **Implement:** wrap openpi `scripts/compute_norm_stats.py` for the PiBot config.
- **Done when:** norm-stats tests green.

### T9.5 — `pibot autonomy record` (teleop demo capture)
- **Files:** `pibot/cli.py` (`autonomy record`); `tests/test_cli_autonomy.py`
- **Test first:** `pibot autonomy record <target> --prompt "follow me" --out demos/` wires teleop (M4) + the `EpisodeLogger` so each teleop step records `(obs, action)`; dispatch + the logger receiving steps is asserted with fakes.
- **Implement:** subcommand combining teleop key→action with obs capture into the logger; classify in the consistency test.
- **Done when:** dispatch + capture-wiring tests green.

### T9.6 — (HIL) Record demonstrations + build dataset
- **Files:** `docs/runbooks/data-collection.md` (procedure + dataset manifest)
- **Procedure:** teleop-record demonstrations for **drive-to-goal**, **follow**, **explore** (count per task = OQ-4); convert → LeRobot dataset; run `compute_norm_stats`; sanity-view a few frames.
- **Done when:** dataset exists with per-task episodes; norm stats computed; manifest recorded.

## Milestone acceptance criteria (SPEC-2 M9)
`PibotInputs`/`PibotOutputs` + norm stats exist; a LeRobot dataset with demonstrations for the three tasks; transforms round-trip an obs→action without shape errors.

## Risks
- **Action-space mapping wrong** (R-8) → T9.3 shape tests + validate against the open-loop server (M8) before recording at scale.
- **Too few demos for a usable fine-tune** (OQ-4) → start with a generous count; M10 will reveal if more are needed.

## Definition of done
Software gates green (incl. the new `server/` tests); HIL dataset recorded + norm stats computed; branch ready to commit (ask first).
