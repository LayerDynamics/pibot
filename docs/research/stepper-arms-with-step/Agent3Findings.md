# Agent 3 Findings — 3D-Model / CAD-Sharing Platforms (GrabCAD, Cults3D, Printables, Thingiverse, MyMiniFactory)

**Facet:** CAD/print-sharing platforms hosting open **stepper** robot arms with a **downloadable STEP (.step/.stp)** file.
**Date:** 2026-06-15. **Researcher:** Research Agent 3 of 4.

## Bottom line — READ THE CAVEATS FIRST

**Major caveat (tooling, not a finding):** the only arms I could machine-verify were on
**Cults3D**, *because* Cults3D rendered to automated fetch while **GrabCAD returned HTTP 403
on every model and `/files` page**. So this result is skewed toward "what the fetch tool
could open," NOT toward "where stepper+STEP arms actually live." **GrabCAD is the platform
most likely to host neutral STEP — and the most likely source of FREE/open STEP — and it is
entirely UNVERIFIED here.** A logged-in human opening GrabCAD's Files tabs is the single
biggest gap to close.

**Second caveat (scope/license):** ExpandedSearches.md's goal is *open-source* stepper arms,
"NOT proprietary." All **3** arms I could verify are **paid + login-gated + Cults PU
(personal-use, NOT open-source / NOT free)**. Against the parent's "download all that have
step" intent, **zero of my verified hits are freely downloadable** — every one paywalls at
the download step. Whether these proprietary paid designs are even in-scope is a judgment
call for the parent; I am NOT presenting them as clean open-source wins.

The 3 I confirmed ship a STEP by reading the actual model pages (all paid, login-gated):

1. **Cults3D SCARA Robot Arm** (4-DOF, 4× NEMA17 stepper) — STEP yes — **paid $8.75**
2. **Cults3D "Robot ARM 6 axis"** by Ruskomponen (6-DOF, NEMA17 stepper) — STEP AP203 + AP214 — **paid $5.81**
3. **Cults3D "6 AXIS ROBOT ARM"** by RiCkY/klabhesh (6-DOF, NEMA17 + NEMA23 stepper) — STEP + STL — **paid $6.58**

Everything else on these platforms was either **STL-only** (no B-rep STEP), **servo**, or a
duplicate of an already-known arm. GrabCAD candidates below are **UNVERIFIED** (do not trust
STEP availability until a human opens them logged-in).

## Findings table

| Model (URL) | Platform | STEP? | Direct link | Login? | DOF | Stepper/servo | License | Note |
|---|---|---|---|---|---|---|---|---|
| [SCARA Robot Arm](https://cults3d.com/en/3d-model/gadget/scara-robot-arm) | Cults3D | **YES** (STEP + STL + SLDPRT/SLDASM) | via page after purchase | **Yes** (paid $8.75) | 4 | **Stepper** (4× NEMA17) | Cults PU (paid, not open) | NEW. Verified page: STEP confirmed. SCARA. |
| [Robot ARM 6 axis](https://cults3d.com/en/3d-model/gadget/robot-arm-6-axis) (Ruskomponen) | Cults3D | **YES** (STEP AP203 + STEP AP214 + SW2020 + STL) | via page after purchase | **Yes** (paid $5.81) | 6 | **Stepper** (NEMA17; GT2 belt + pulleys) | Cults PU (paid, not open) | NEW. Verified page lists both STEP AP203 & AP214. Assembly vid youtu.be/hQ5vphYN9Fo. |
| [6 AXIS ROBOT ARM](https://cults3d.com/en/3d-model/gadget/6-axis-robot-arm-klabhesh) (RiCkY/klabhesh) | Cults3D | **YES** (STEP + STL; SW2020 on request) | via page after purchase | **Yes** (paid $6.58+) | 6 | **Stepper** (NEMA17 + NEMA23, planetary gearboxes) | Cults PU (paid, not open) | NEW. Verified page: STEP confirmed. Arduino code included. |
| [6-axis Robot Arm Model](https://cults3d.com/en/3d-model/gadget/robot-arm-model-6-axis-3d-printable) (3Ddynamics) | Cults3D | YES (STEP + STL) | n/a | Yes (paid $3.43) | 6 | **SERVO** ("six servo axes") | Cults PU | **EXCLUDE — servo**, not stepper. Has STEP but out of scope. |
| [6 Axis Robot Arm — NKL Robotic Arm V1](https://cults3d.com/en/3d-model/gadget/6-axis-robot-arm-nkl-robotic-arm-v1) | Cults3D | **STL-only** (STL/RAR/ZIP, no STEP) | n/a | Yes (paid $13.95) | 6 | Stepper (NEMA11/17) | Cults PU | **EXCLUDE — no STEP** (mesh only). |
| [CyBot — Cycloidal Disk Robot arm](https://cults3d.com/en/3d-model/gadget/cybot-cycloidal-disk-robot-arm) (quartit) | Cults3D | **STL-only** (STL + PDF + URDF, no STEP) | n/a | Yes (paid $29.07) | 6 | Stepper (NEMA17, cycloidal) | Cults PU | **EXCLUDE — no STEP**. Also mirrored on Thingiverse:5142762 & Hackaday 182821. Cross-ref Agent for cycloidal facet. |
| [6-axis robotic arm](https://www.printables.com/model/742414-6-axis-robotic-arm/files) | Printables | **STL-only** (STL/3MF; PDF + code .txt) | free | likely (free) | 6 | unspecified on page | unknown | **EXCLUDE — no STEP found** on Files tab (mesh only). |
| [Nema 17 Robot Arm remix](https://www.thingiverse.com/thing:5672870) (BookedDolphin) | Thingiverse | **STL-only** (typical Thingiverse) | free | no | ~5-6 | Stepper (NEMA17, LoboCNC planetary) | CC (Thingiverse default) | **EXCLUDE — STL-only**. Thingiverse is mesh-only. |
| [Robotic Arm with NEMA 17 stepper motors](https://grabcad.com/library/robotic-arm-with-nema-17-stepper-motors-1) | GrabCAD | **UNVERIFIED** (403; GrabCAD usually STEP) | Files tab after login | Yes (free account) | ~5-6 | Stepper (NEMA17) | GrabCAD ToS | NEW candidate, **could not verify** file list (403). GrabCAD typically offers STEP/IGES. |
| [3D printable Stepper powered Robotic Arm — AR3 variation](https://grabcad.com/library/3d-printable-stepper-powered-robotic-arm-ar3-variation-1) | GrabCAD | **UNVERIFIED** (403) | Files tab after login | Yes (free account) | 6 | Stepper | GrabCAD ToS | **DUPLICATE** of AR3 (already known). Skip unless STEP differs. |
| [6-Axis Robotic Arm](https://grabcad.com/library/6-axis-robotic-arm-2) | GrabCAD | **UNVERIFIED** (403) | [/files](https://grabcad.com/library/6-axis-robotic-arm-2/files) after login | Yes (free account) | 6 | unspecified | GrabCAD ToS | NEW candidate, unverified. Motor type unknown — verify stepper before use. |
| [6-axis stepper robot](https://grabcad.com/library/6-axis-stepper-robot-1) | GrabCAD | **UNVERIFIED** (403) | Files tab after login | Yes (free account) | 6 | Stepper (per title) | GrabCAD ToS | NEW candidate (2016). Title says stepper; STEP unverified (403). |
| [Actuator-Operated Robotic Arm](https://grabcad.com/library/actuator-operated-robotic-arm-1) | GrabCAD | **UNVERIFIED** (403) | [/files](https://grabcad.com/library/actuator-operated-robotic-arm-1) after login | Yes (free account) | ? | "actuator" (likely linear actuators, NOT stepper) | GrabCAD ToS | Likely out of scope (actuator-driven). Verify before use. |
| [Robotic arm modelled after open source uArm](https://grabcad.com/library/robotic-arm-modelled-after-open-source-uarm-1) | GrabCAD | **UNVERIFIED** (403) | Files tab after login | Yes (free account) | 4 | uArm = **stepper/servo mix** (uArm uses steppers) | GrabCAD ToS | uArm clone. Verify motor + STEP. |

## What to actually download (in-scope, verified)

Only the three top Cults3D rows are confirmed **stepper + STEP**. All three are **paid** and
require a **Cults3D login/purchase** — there is no anonymous direct-download link; the STEP
is delivered through the model page after purchase. None are open-source-licensed (Cults PU
= personal-use, paid). If the intention is "use only the geometry and remake all other
logic," the STEP geometry from these is usable, but the **license is restrictive** (paid
personal-use, not CC/open) — confirm licensing is acceptable before relying on them.

## Honesty notes (per the no-fabrication rule)

- **GrabCAD rows are UNVERIFIED.** GrabCAD returned HTTP 403 to automated fetch on every
  model and `/files` page, so I could not read the actual file list. GrabCAD *usually* ships
  STEP/IGES, but I did **not** confirm a STEP exists for any specific GrabCAD arm above. A
  human with a (free) GrabCAD account must open the Files tab to confirm.
- **Printables and Thingiverse are mesh-only in practice.** Every print-site arm I checked
  was STL/3MF (and PDF/code), **no B-rep STEP**. I found **zero** in-scope stepper+STEP arms
  on Printables, Thingiverse, or MyMiniFactory.
- **MyMiniFactory:** no stepper robot-arm-with-STEP result surfaced at all.
- The Ruskomponen and RiCkY arms appear to be the **same family of commercial Cults3D
  designs** (both sell SW2020 + STEP + STL bundles, both 6-axis NEMA-stepper, both offer
  email/WhatsApp support). Treat as two distinct listings but likely related sellers.
- CyBot is **already covered** by the cycloidal/Hackaday facet; flagged here only to record
  it is **STL-only** on Cults3D (no STEP), so it does NOT satisfy the STEP requirement from
  this platform.
