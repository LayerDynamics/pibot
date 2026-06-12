"""Runtime-hardening config builders — the research reflash recipe, as code.

Pure, idempotent string transforms (no I/O) that bake the mobile-robot reliability
recipe into the Pi's boot/OS config. They are applied at flash first-boot and by deploy:

  - **NVMe ASPM fix** (``cmdline.txt``): ``pcie_aspm=off`` +
    ``nvme_core.default_ps_max_latency_us=0`` — the #1 runtime killer is PCIe ASPM / NVMe
    power-save dropping the controller and remounting root read-only mid-operation.
  - **Hardware watchdog** (``config.txt``): ``dtparam=watchdog=on`` so the kernel exposes
    ``/dev/watchdog`` for systemd's ``RuntimeWatchdogSec`` (wired in T7.4).
  - **journald volatile** (drop-in): keep logs in RAM (shipped off-box over Nebula) so the
    NVMe isn't written on every log line.
  - **Persistent rw partition** (``fstab``): a small ext4 ``/var/lib/pibot`` that survives an
    overlayfs read-only root — for Nebula certs, the model cache, calibration, datasets.

ext4 (not f2fs) per the research: f2fs discards already-``fsync``'d data under power loss.
The overlayfs read-only-root flip itself is a runtime step (raspi-config), done in the T7.6
HIL procedure; everything emitted here is plain config text.
"""

from __future__ import annotations

# NVMe / PCIe boot args (cmdline.txt) — the ASPM + power-save fix.
CMDLINE_ARGS: tuple[str, ...] = ("pcie_aspm=off", "nvme_core.default_ps_max_latency_us=0")

# Boot config (config.txt) directives.
CONFIG_TXT_LINES: tuple[str, ...] = ("dtparam=watchdog=on",)

# The persistent read-write partition that outlives the overlayfs root.
RW_DIR = "/var/lib/pibot"
RW_PARTLABEL = "pibotdata"
JOURNALD_RUNTIME_MAX = "64M"


def apply_cmdline(cmdline: str) -> str:
    """Return ``cmdline.txt`` with the NVMe/ASPM args appended (idempotent, single line)."""
    tokens = cmdline.split()
    for arg in CMDLINE_ARGS:
        if arg not in tokens:
            tokens.append(arg)
    return " ".join(tokens)


def apply_config_txt(config_txt: str) -> str:
    """Return ``config.txt`` with the hardening directives appended (idempotent)."""
    out = config_txt if config_txt.endswith("\n") or not config_txt else config_txt + "\n"
    existing = set(out.splitlines())
    for line in CONFIG_TXT_LINES:
        if line not in existing:
            out += line + "\n"
    return out


def journald_dropin() -> str:
    """A ``/etc/systemd/journald.conf.d`` drop-in: volatile storage, capped RAM use."""
    return (
        "# PiBot: keep journald in RAM (shipped off-box over Nebula) to spare the NVMe.\n"
        "[Journal]\n"
        "Storage=volatile\n"
        f"RuntimeMaxUse={JOURNALD_RUNTIME_MAX}\n"
    )


def fstab_snippet(rw_dir: str = RW_DIR) -> str:
    """An ``fstab`` snippet: tmpfs for scratch + the persistent ext4 ``rw`` partition.

    The root mount keeps ``noatime,commit=3`` (short commit window bounds data-at-risk on
    a power-loss-prone robot); ``rw_dir`` is the small ext4 partition that survives an
    overlayfs read-only root.
    """
    return (
        "# PiBot hardening (see pibot.provision.hardening)\n"
        "tmpfs  /tmp      tmpfs  defaults,noatime,nosuid,size=64m   0  0\n"
        "tmpfs  /var/log  tmpfs  defaults,noatime,nosuid,size=32m   0  0\n"
        f"PARTLABEL={RW_PARTLABEL}  {rw_dir}  ext4  defaults,noatime,commit=3  0  2\n"
    )


def directives() -> list[str]:
    """Human-readable summary of every change this module applies (for runbooks/logs)."""
    return [
        f"cmdline.txt: append {' '.join(CMDLINE_ARGS)}  (NVMe ASPM / power-save fix)",
        *(f"config.txt: ensure {line}  (hardware watchdog)" for line in CONFIG_TXT_LINES),
        f"journald: Storage=volatile, RuntimeMaxUse={JOURNALD_RUNTIME_MAX}  (spare the NVMe)",
        f"fstab: tmpfs /tmp + /var/log; persistent ext4 {RW_DIR} (noatime,commit=3)",
    ]
