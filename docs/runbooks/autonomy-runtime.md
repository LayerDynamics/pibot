# Runbook — Autonomy runtime: reflash, harden, prove the pipe (M7 T7.6)

The hardware gate for M7: reflash the Pi to the researched baseline, apply the hardening
the M7 software builders emit, and prove the openpi policy websocket round-trips. This
**fixes the SSH lockout** (fresh image with first-boot key embedding) and makes the Pi a
runtime autonomy can be trusted on.

> **Status: PENDING — not yet run on hardware.** Needs the Pi at the bench. The software
> that produces this config is built and gate-green (`pibot.provision.hardening`,
> `pibot.deploy.service` renderers, `tools/pipe_check.py`); the steps below apply it.

## Prerequisites
- The Pi's NVMe reachable for flashing (USB-C rpiboot, or pull the drive).
- Nebula overlay up Mac↔Pi ([nebula-overlay.md](nebula-overlay.md)); the M4 Max serving a
  stock π₀.₅ ([PIML.md §6](../../PIML.md)).
- Research recipe: `.web-research/best-os-install-pi5-robot-2026-06-11/Report-Final.md`.

## 1. Reflash to the hardened baseline (Raspberry Pi OS Lite 64-bit)
```bash
pibot flash --target nvme --os rpi-os \
  --authorized-key-file ~/.ssh/id_ed25519.pub --hostname pibot --confirm
```

## 2. Apply the runtime hardening
The exact directives come from the M7 builders — review them, then apply on the Pi:
```bash
python -c "from pibot.provision import hardening; print(chr(10).join(hardening.directives()))"
```
On the Pi (`/boot/firmware/`): append `hardening.apply_cmdline()`'s args to `cmdline.txt`
(`pcie_aspm=off nvme_core.default_ps_max_latency_us=0`) and `hardening.apply_config_txt()`'s
lines to `config.txt` (`dtparam=watchdog=on`); install the `journald_dropin()` and
`fstab_snippet()` (persistent ext4 `/var/lib/pibot`); enable overlayfs read-only root
(`raspi-config` → Performance → Overlay File System) keeping `/var/lib/pibot` writable.
Install the systemd units from `pibot.deploy.service`: `render_watchdog_conf()`
(`RuntimeWatchdogSec=14`) and `render_nebula_unit()` (`Restart=always`).

## 3. Install the on-robot ML client
```bash
pibot deploy pibot          # syncs the package + venv
# on the Pi: install the optional ML stack into the venv
/opt/pibot/venv/bin/pip install -e '/opt/pibot/current[ml]'
```

## Verify
```bash
pibot run pibot -- whoami                      # 1. SSH-key login works (lockout fixed)
pibot run pibot -- "dmesg | grep -i nvme"      # 2. no controller-down / read-only remount
# 3. yank power x5 between commands -> rootfs stays intact (overlayfs)
python tools/pipe_check.py --host 192.168.100.1 --port 8000 --rounds 50   # 4. pipe round-trips
```

## Results
| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | SSH-key login (lockout fixed) | ✅ 2026-06-13 | key-only (`passwordauthentication no`); deploy + all ops run over SSH keys |
| 2 | NVMe clean under load (ASPM fix) | ✅ 2026-06-13 | `dmesg` clean — no AER/controller errors on Ubuntu 24.04 (NVMe root, 235G) |
| 3 | Power-yank ×5, rootfs intact | ⬜ pending | needs physical power-cycling. **Note:** this Ubuntu rootfs is plain ext4 (the Bookworm overlayfs RO-root was *not* ported), so power-loss durability is a real risk area to verify/harden |
| 4 | pipe_check round-trips + latency | ✅ 2026-06-13 | Pi→Mac over **Nebula**, 50 rounds: min 13 / median 19 / **p95 53 ms**; chunk (50,8). Stub policy server (`~/.config/pibot/policy-stub/`) — pipe/serialization latency, **not** model inference |
