# Plan — M8: Camera & Observation Pipeline (Open Loop)

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

| | |
|---|---|
| **Spec** | [SPEC-2](../specs/SPEC-2-pibot-autonomy-platform.md) §3.2, §4.1 Phase B, FR-1/2/11, Appx B |
| **Milestone** | M8 |
| **Depends on** | M7 (runtime + pipe) |
| **Branch** | `m8-camera-open-loop` |
| **Date** | 2026-06-11 |
| **Status** | Not started (planned — no code yet) |

**Goal:** Stream **real** camera observations to a stock π₀.₅ server and log the returned actions — with **zero actuation** (the hard gate before any closed-loop motion).
**Architecture:** A USB-UVC camera module → `image_tools.resize_with_pad` 224×224; typed `Observation`/`Action` (contract-first, Appx B); `PibotEnvironment.get_observation`; an open-loop runner whose `apply_action` logs only.
**Practices:** TDD + contract-first + typed-first; SPEC-1 gates; the live camera/server step is a gated HIL procedure.

## Goal
Validate the observation schema, image pipeline, and end-to-end latency on real data — without the robot ever moving.

## In scope
Camera module; obs/action types; `PibotEnvironment.get_observation`; open-loop Runtime wiring (log-only `apply_action`); `pibot autonomy --open-loop` CLI; the live HIL open-loop run.

## Out of scope
Actuation / `apply_action` → transport (M10). Server transforms + data collection (M9). Fine-tuning (M10).

## Prerequisites
- M7 done (pipe proven, `pibot[ml]` installed on the Pi).
- A USB UVC camera at `/dev/video0` (OQ-3: model/mount).

## Tasks

### T8.1 — Observation/Action contract types (contract-first, typed-first)
- **Files:** `pibot/ml/types.py`; `tests/test_ml_types.py`
- **Test first:** `Observation` carries `image:{base_0_rgb: uint8[224,224,3]}, state: list[float], prompt: str`; `to_dict()` matches SPEC-2 Appendix B exactly (assert keys/shapes); `Action.from_reply(reply)` slices `actions[step]`.
- **Implement:** frozen dataclasses + `to_dict`/`from_reply`.
- **Done when:** type tests green; dict round-trips the Appx B schema.

### T8.2 — Camera module (USB UVC)
- **Files:** `pibot/ml/camera.py`; `tests/test_camera.py`
- **Test first:** with an **injected fake capture** returning an arbitrary HxWx3 frame, `Camera.capture()` returns `uint8[224,224,3]` (square via `resize_with_pad`); `is_open`/`close` behave; a capture failure raises a clear error (not a silent black frame).
- **Implement:** `cv2.VideoCapture` behind a `capture_fn` seam; `openpi_client.image_tools` for resize/convert; lazy imports.
- **Done when:** camera tests green (no hardware).

### T8.3 — `PibotEnvironment.get_observation`
- **Files:** `pibot/ml/pibot_environment.py`; `tests/test_pibot_environment.py`
- **Test first:** with a fake camera + fake telemetry source, `get_observation()` returns the Appx B dict (image from camera, `state` from telemetry fields per OQ-2, `prompt` from config); `reset()` issues a stop.
- **Implement:** implement the openpi `Environment` ABC `reset`/`is_episode_complete`/`get_observation` (apply_action stub raises `NotImplementedError("M10")` — open-loop overrides it; documented, not a silent stub).
- **Done when:** env tests green.

### T8.4 — Open-loop runner (log-only, NO actuation)
- **Files:** `pibot/ml/openloop.py`; `tests/test_openloop.py`
- **Test first:** wire a `Runtime` with a **fake `WebsocketClientPolicy`** (canned chunks) + `ActionChunkBroker(horizon=50)`; the open-loop `apply_action` records each action to an `EpisodeLogger`-shaped sink and **never calls `transport.send`** (assert the transport received nothing across many steps). FR-11/FR-4 safety: log-only path proven.
- **Implement:** an `OpenLoopEnvironment(PibotEnvironment)` overriding `apply_action` to log only; the broker/runtime wiring.
- **Done when:** open-loop test green; transport untouched.

### T8.5 — `pibot autonomy --open-loop` CLI
- **Files:** `pibot/cli.py` (new `autonomy` subcommand); `tests/test_cli_autonomy.py`
- **Test first:** `pibot autonomy <target> --open-loop --prompt "drive to the red ball"` dispatches to the open-loop runner with the parsed prompt/host; classified READ-ish in the consistency test (no actuation → no `--dry-run` required; document the classification).
- **Implement:** subcommand + handler (lazy ml import); add to `tests/test_cli_consistency.py` classification.
- **Done when:** dispatch + consistency tests green.

### T8.6 — (HIL) Real open-loop run
- **Files:** `docs/runbooks/autonomy-bringup.md` (procedure + results)
- **Procedure:** real camera at `/dev/video0`; M4 Max serving a **stock** `lerobot/pi05_base`; run `pibot autonomy --open-loop`; confirm ≥15 fps capture, obs schema accepted by the server, end-to-end latency on real data; **verify zero actuation** (motors never move; transport log shows no drive frames).
- **Done when:** real obs accepted; latency recorded; camera ≥15 fps; zero actuation confirmed.

## Milestone acceptance criteria (SPEC-2 M8)
Obs schema validated against the server; image pipeline ≥15 fps; end-to-end latency on real data measured; zero actuation.

## Risks
- **USB camera latency/quality** (R-6) → measure obs-assembly ≤50 ms; if poor, flag a switch to Pi Camera Module 3 (OQ-3).
- **Server rejects obs shape** → contract test (T8.1) catches schema drift before HIL.

## Definition of done
Software gates green; HIL open-loop run recorded with zero actuation; branch ready to commit (ask first).
