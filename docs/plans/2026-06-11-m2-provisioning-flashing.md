# Plan — M2: Provisioning & Flashing

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-3, §6.6 |
| **Milestone** | M2 |
| **Depends on** | M1 |
| **Branch** | `m2-provisioning-flashing` |
| **Date** | 2026-06-11 |
| **Status** | Not started |

> Conventions per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).
> **This milestone writes to disks and bootloaders — the wrong-disk guard (T2.1) and
> `--dry-run`/`--confirm` are mandatory, not optional.**

## Goal
The full provisioning surface: reflash the onboard NVMe over USB-C (`rpiboot`
mass-storage + `rpi-imager`), flash removable media, write headless first-boot config,
manage the `rpi-eeprom` bootloader/`BOOT_ORDER`, clone/restore the NVMe, and build/flash
Arduino firmware.

## In scope
`flash` (host mass-storage + removable), first-boot config writer, `eeprom`,
`provision clone/restore`, `firmware build/flash`.

## Out of scope
Robot control/protocol (M3+).

## Prerequisites & verified facts
- `rpiboot`/`usbboot` and `rpi-imager` are **not installed** on the Mac (verified
  2026-06-11). **T2.0 installs them.**
- Verified command syntax (from SPEC-1 §15 sources):
  - `rpiboot -d mass-storage-gadget64` puts a connected Pi 5 into USB mass-storage
    mode; **Pi 5 has no nRPIBOOT jumper — hold the power button while connecting
    USB-C**.
  - `rpi-imager --cli [--quiet] [--disable-verify] [--sha256 <hash>]
    [--secure-boot-key <key>] <image-uri> <destination-device>`.
  - On-Pi: `rpi-eeprom-update -a`, `rpi-eeprom-config --edit` (BOOT_ORDER, e.g.
    NVMe-first `0xf416`).

## Tasks

### T2.0 — Tooling install + capability probe
- **Files:** `scripts/install-flash-tools.sh`, `pibot/provision/tools.py`
- **Test first:** `tests/test_provision_tools.py` — `require_tool('rpiboot')` raises a
  clear `PibotError` with install hint when absent; returns path when present (fake PATH).
- **Implement:** build `usbboot` from source (clone, `make`) and install `rpi-imager`
  (Homebrew cask or official build) via the script; `tools.py` resolves/validates the
  binaries and surfaces actionable errors.
- **Done when:** probe tests green; running the script makes `rpiboot --version`/
  `rpi-imager --version` resolve (manual/host step, asserted by a follow-up probe).

### T2.1 — Device enumeration + safety guards (pure, exhaustively TDD)
- **Files:** `pibot/provision/devices.py`
- **Test first:** `tests/test_devices.py` — parse `diskutil list -plist` (macOS) and
  `lsblk -J` (Linux) fixtures into device records; **`assert_safe_target` REFUSES**:
  the system/boot disk, mounted-as-`/` disks, disks whose size/model don't match the
  expected external NVMe/SD; **accepts** only a confirmed external target; `diff_new_device`
  identifies the device that appeared after `rpiboot`.
- **Implement:** parsers + guard logic + before/after enumeration diff. No execution.
- **Done when:** every refuse/accept branch covered, including ambiguous (>1 new
  device) → error.

### T2.2 — Removable-media flash (`flash --device`)
- **Files:** `pibot/provision/imager.py`, `pibot/provision/flash.py`
- **Test first:** `tests/test_imager.py` — builds `rpi-imager --cli` argv with
  `--sha256` when given; macOS path uses `/dev/rdiskN` + `diskutil unmountDisk` first;
  `--dry-run` prints the exact argv and writes nothing; `--disable-verify` honored.
- **Implement:** `rpi-imager` wrapper + macOS raw-disk handling; `flash --device DEV
  --image URI [--sha256 H] [--dry-run] [--confirm]` gated by T2.1.
- **Done when:** argv + dry-run + macOS-rdisk tests green.

### T2.3 — Host mass-storage flash (`flash --target nvme|sd`)
- **Files:** `pibot/provision/rpiboot.py`, extend `flash.py`
- **Test first:** `tests/test_rpiboot.py` — orchestration with fakes: runs `rpiboot -d
  mass-storage-gadget64`, polls `diff_new_device` until the block device enumerates
  (timeout → error), confirms it via T2.1, then delegates to T2.2; `--dry-run` prints
  the full sequence incl. the power-button-hold instruction.
- **Implement:** the mass-storage orchestration; user-facing prompt to hold the power
  button while connecting USB-C (Pi 5).
- **Done when:** orchestration + timeout + dry-run tests green.

### T2.4 — First-boot config writer
- **Files:** `pibot/provision/firstboot.py`
- **Test first:** `tests/test_firstboot.py` — given a config (hostname, wifi creds,
  enable-ssh, user, authorized key, locale, `enable_uart`), generates correct
  `custom.toml`/`firstrun.sh` + `cmdline.txt` edits and the boot-partition file layout;
  secrets never logged.
- **Implement:** mount the freshly-written boot partition and apply headless config
  (rpi-imager CLI does **not** expose these — we own it).
- **Done when:** generation tests green for every field; redaction asserted.

### T2.5 — `pibot eeprom status|update|config|boot-order` (over SSH)
- **Files:** `pibot/provision/eeprom.py`
- **Test first:** `tests/test_eeprom.py` — builds the right on-Pi commands
  (`rpi-eeprom-update -a`, `rpi-eeprom-config --edit`/`--apply`); parses
  `rpi-eeprom-update` status output; `boot-order 0xf416` validation; destructive ops
  require `--confirm`.
- **Implement:** SSH-driven (reuses M1 runner) read/update/config + BOOT_ORDER set with
  reboot orchestration and post-reboot health re-check.
- **Done when:** parse/validate/confirm tests green; integration read-only `status`
  against the real Pi (marked hardware).

### T2.6 — `pibot provision clone` / `restore`
- **Files:** `pibot/provision/clone.py`
- **Test first:** `tests/test_clone.py` — builds the on-Pi image pipeline (quiesce
  `pibotd` if present, copy mounted fs to a sparse image, shrink, compress), streams
  back via M1 `pull`; `restore` validates the image and reverses it behind `--confirm`.
- **Implement:** clone/restore orchestration over SSH.
- **Done when:** orchestration tests green; integration clone of a tiny partition vs the
  Pi (hardware-marked).

### T2.7 — `pibot firmware build|flash` (arduino-cli)
- **Files:** `pibot/provision/firmware.py`
- **Test first:** `tests/test_firmware.py` — builds `arduino-cli compile`/`upload` argv
  for a given FQBN + port; resolves the port from the active transport config; run
  locally (Mac-wired) or over SSH (Pi-wired) selectable.
- **Implement:** arduino-cli wrapper for build + upload.
- **Done when:** argv tests green (compile-on-CI of the M3 reference sketch lands in M3/M6).

## Milestone acceptance criteria (SPEC-1 §8 M2)
- Onboard NVMe reflashed end-to-end over USB-C (real-hardware E2E, documented).
- `--dry-run` prints exact external commands for every flash path.
- Wrong-disk guard refuses the system disk (unit-proven).
- EEPROM `boot-order` read/write verified.
- All gates green.

## Risks
- **Destroying host data by flashing the wrong disk** → T2.1 guard + size/model match
  + `--confirm` + `--dry-run`; unit tests assert refusal of the system disk.
- **rpiboot won't enter mass-storage on Pi 5** → explicit power-button-hold prompt;
  timeout with guidance; documented in `docs/runbooks/flash.md` (M6).
- **Bad EEPROM config bricks boot** → `--confirm`, preserve prior config, recovery via
  SD/USB recovery image (runbook).
- **macOS raw-disk permissions** → use `/dev/rdiskN`, unmount first; detect EPERM and
  instruct.

## Definition of done
All gates pass; acceptance met; destructive-path guards unit-proven; hardware E2E
reflash performed and recorded; branch ready to commit (ask first).
