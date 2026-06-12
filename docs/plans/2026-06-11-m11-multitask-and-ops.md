# Plan — M11: Multi-Task & Operability

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

| | |
|---|---|
| **Spec** | [SPEC-2](../specs/SPEC-2-pibot-autonomy-platform.md) §3.9, §4.1 Phase E, FR-9/13, §5 M11, §6 |
| **Milestone** | M11 (final SPEC-2 milestone) |
| **Depends on** | M10 (closed-loop, single task) |
| **Branch** | `m11-multitask-ops` |
| **Date** | 2026-06-11 |
| **Status** | Software shipped (T11.1–T11.3, T11.5, gate-green 626 passed); HIL pending hardware (T11.4 multi-task demos+fine-tune, T11.6 autonomy E2E sign-off — runbooks/sign-off written PENDING). **SPEC-2 software complete.** Known gap: T11.1's policy-link schema/render/threshold/CSV are done + unit-proven, but the live feed into pibotd's `/telemetry` is **not wired** (the autonomy runner is a separate process; `pibot monitor` shows `connected=None`). Live policy health is in the runner's logs. Resolving it needs the in-process-vs-standalone autonomy decision — see [autonomy-e2e-signoff.md](../autonomy-e2e-signoff.md) "Open decision". |

**Goal:** All three prompted behaviors (drive-to-goal, follow, explore) plus the operability to run autonomy with confidence — policy-link telemetry, log-shipping, runbooks, and a hardware sign-off.
**Architecture:** Extend telemetry with policy-link health; ship journald to the Mac over Nebula; per-task prompts; expand demos/fine-tune to cover follow + explore; write the autonomy runbooks.
**Practices:** TDD + typed-first; SPEC-1 gates + doc-lint on runbooks; the multi-task fine-tune + full E2E are gated HIL procedures.

## Goal
Turn a one-task demo into a trustworthy, observable multi-task autonomous robot.

## In scope
Policy-link telemetry + monitor render; log-shipping config; per-task prompt support; multi-task demos/fine-tune (HIL); autonomy runbooks; full-E2E hardware sign-off.

## Out of scope
New tasks beyond the three; an MLX serving port (OQ-6, future); fleet anything (non-goal).

## Prerequisites
- M10 done (closed-loop proven on ≥1 task).

## Tasks

### T11.1 — Policy-link telemetry in the snapshot
- **Files:** `agent/telemetry.py` (+ `policy` block), `pibot/monitor.py` (render); `tests/test_telemetry.py`, `tests/test_monitor.py`
- **Test first:** the `/telemetry` snapshot gains `policy: {connected, last_inference_ms, chunk_age_ms}`; `check_thresholds` flags `policy down` / stale chunk; `render_snapshot` shows the policy line; `--json` includes it.
- **Implement:** populate the block from the runtime/broker state; extend the renderer + CSV fields.
- **Done when:** telemetry + monitor tests green.

### T11.2 — Log-shipping to the Mac (config builder)
- **Files:** `pibot/provision/hardening.py` (+ `render_log_upload`), `tests/test_hardening.py`
- **Test first:** the builder emits a `systemd-journal-upload`/rsync drop-in pointing at the Mac's Nebula IP (assert the URL/host token); journald stays `Storage=volatile` locally.
- **Implement:** config builder (pure string), reused by deploy.
- **Done when:** builder test green (research log-shipping recommendation).

### T11.3 — Per-task prompt support
- **Files:** `pibot/ml/openloop.py` / closed-loop runner, `pibot/config.py`; `tests/test_cli_autonomy.py`
- **Test first:** `--prompt` selects the behavior at run time across all three task strings; a `--task {goal,follow,explore}` shorthand maps to the canonical prompt; the runner forwards the prompt into every observation (assert on fakes).
- **Implement:** prompt plumbing + the task→prompt map.
- **Done when:** prompt-routing tests green (FR-9).

### T11.4 — (HIL) Multi-task demos + fine-tune
- **Files:** `docs/runbooks/data-collection.md` (append), `finetune-and-serve.md` (append)
- **Procedure:** record demonstrations for **follow** and **explore** (counts per OQ-4); re-fine-tune covering all three tasks; serve; verify each prompt produces its behavior closed-loop.
- **Done when:** all three prompts drive the robot; results recorded.

### T11.5 — Autonomy runbooks
- **Files:** `docs/runbooks/autonomy-bringup.md`, `data-collection.md`, `finetune-and-serve.md` (finalize); `tests/test_docs.py` (add to RUNBOOKS)
- **Test first:** add the three runbooks to the doc-lint RUNBOOKS list — each must end with a `## Verify` step + have language-tagged fences + resolving links (existing `test_docs.py` machinery).
- **Implement:** finalize the runbooks (verify steps mapping to real `pibot autonomy` commands).
- **Done when:** doc-lint green over the new runbooks.

### T11.6 — (HIL) Full autonomy E2E sign-off
- **Files:** `docs/autonomy-e2e-signoff.md` (procedure + results table)
- **Procedure:** end-to-end on the robot — reflashed runtime → camera → M4 Max policy → all three prompted behaviors closed-loop → drop-to-stop → policy-link telemetry visible → power-loss survived. Record each result; mark PENDING until run (honest, like the SPEC-1 hardware sign-off).
- **Done when:** the sign-off table is filled on hardware (or recorded PENDING with the gap stated).

## Milestone acceptance criteria (SPEC-2 M11)
drive-to-goal + follow + explore all work from their prompts; policy-link telemetry + log-shipping in place; runbooks lint-clean; the autonomy E2E sign-off is recorded.

## Risks
- **One task regresses when fine-tuning for three** (catastrophic forgetting) → keep per-task eval; if needed, per-task checkpoints selected by prompt.
- **Sign-off claimed without hardware** → T11.6 is explicit; mark PENDING rather than overclaim (SPEC-1 honesty precedent).

## Definition of done
Software gates green; doc-lint green; multi-task behavior demonstrated; E2E sign-off recorded (or PENDING with the gap stated); branch ready to commit (ask first). **SPEC-2 complete.**
