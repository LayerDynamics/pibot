# Plan — M-ARM-6: 3-D twin (SPEC-4)

> **For Claude:** execute with `lore:execute`. **TDD mandatory** (failing test first → implement →
> desktop gate green). Shared decisions/discipline/invariants: see the
> [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Render a live 3-D twin of the arm in the Mission Control Arm screen — the M-ARM-3 URDF loaded with
`urdf-loader` + three.js, joints driven by live telemetry, with an optional interactive gizmo that
emits jog/IK intents through the control surface (the 6AR pattern, `OtherArms §8`).

## Realizes

- SPEC-4 **FR-18**; closes `OtherArms.md` **§6B-5** (no 3-D visualization / digital twin).

## Depends on / blocks

- **Depends on:** M-ARM-3 (the in-tree URDF + meshes). The optional gizmo (6.4) also uses M-ARM-1
  (jog) and M-ARM-4 (Cartesian/IK).
- **Blocks:** nothing.

## Tasks

### 6.1 — App dependencies

- **What:** add `urdf-loader`, `three`, `@react-three/fiber`, and `@react-three/drei` to
  `app/package.json`; refresh the lockfile with `pnpm install --frozen-lockfile` (update the lockfile in
  the same change).
- **Files:** `app/package.json`, `app/pnpm-lock.yaml`.
- **Test-first:** a minimal import/render smoke test (vitest) for the new three.js scene wrapper so the
  dependency wiring is verified before building the twin.
- **Done when:** deps install; smoke test renders an empty scene; `pnpm typecheck`/`build` green.

### 6.2 — Ship the model to the app

- **What:** make the M-ARM-3 URDF + meshes loadable by the app — copy/symlink into `app/public/arm/`
  (or serve them from the sidecar via a static route) and document the resolved path.
- **Files:** `app/public/arm/` (URDF + meshes), or a sidecar static route + `app/src` loader path.
- **Test-first:** a loader test asserting the URDF path resolves and parses to the expected joint set.
- **Done when:** the app can fetch + parse the in-tree URDF; desktop gate green.

### 6.3 — Twin component

- **What:** in `app/src/screens/Arm.tsx`, add a 3-D twin — load the URDF via `urdf-loader` + three.js,
  drive each joint from live telemetry (~30 Hz), color-code joints approaching their limits, and overlay
  the EE pose (from M-ARM-3 FK). Degrade gracefully (no model configured → keep the existing bar view,
  no crash).
- **Files:** `app/src/screens/Arm.tsx`, a new `app/src/screens/arm/ArmTwin.tsx` component,
  `app/src/stores/armStore.ts`.
- **Test-first:** extend `app/src/stores/armStore.test.ts` + a component test with mock telemetry —
  joint values map onto the loaded model; near-limit color logic; absent-model fallback.
- **Done when:** the twin tracks live telemetry at ≥10 Hz; desktop gate green.

### 6.4 — Optional interactive gizmo

- **What:** add an interactive joint/TCP gizmo that, on drag, emits jog intents (M-ARM-1) or a Cartesian
  move (M-ARM-4) through the control surface.
- **Files:** `app/src/screens/arm/ArmTwin.tsx`, `app/src/stores/armStore.ts`.
- **Test-first:** store test — a gizmo drag dispatches the correct `move`/`move-cartesian` action.
- **Done when:** the gizmo drives the arm through the surface; desktop gate green.

### 6.5 — Docs

- **What:** mark `OtherArms.md` §6B-5 shipped; note the twin + its model path in `CLAUDE.md`'s app
  section.
- **Files:** `docs/research/stepper-robot-arms-github/OtherArms.md`, `CLAUDE.md`.
- **Done when:** docs accurate (NFR-8).

## Milestone DoD

A live URDF twin renders in the Arm screen at ≥10 Hz driven by telemetry; the optional gizmo emits
intents through the control surface; absent-model fallback works; `pnpm` desktop gate (vitest + tsc +
eslint) green.

## Notes / risks

- The app is already React 19 + capable of bundling three.js — keep the twin lazy-loaded so it doesn't
  bloat the initial bundle for users without an arm configured.
- Reuse the existing telemetry poll/store; do not open a second telemetry channel for the twin.
- Keep mesh assets reasonable — prefer primitive collisions / decimated visual meshes if the donor STLs
  are heavy.
