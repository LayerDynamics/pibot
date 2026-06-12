"""T7.3 — runtime-hardening config builders (the research reflash recipe as code).

Pure string builders (no I/O) that emit the boot/OS hardening for a mobile-robot Pi:
the NVMe ASPM fix (the #1 runtime killer), the hardware watchdog dtparam, journald
volatile, and a small persistent rw partition. Reused by the flash first-boot config
and the deploy. Idempotent so re-applying never duplicates lines.
"""

from __future__ import annotations

from pibot.provision import hardening


def test_cmdline_adds_nvme_aspm_fix_idempotently() -> None:
    base = "console=serial0,115200 root=PARTUUID=abcd-02 rootwait"
    out = hardening.apply_cmdline(base)
    assert "pcie_aspm=off" in out
    assert "nvme_core.default_ps_max_latency_us=0" in out
    assert out.count("pcie_aspm=off") == 1
    assert hardening.apply_cmdline(out) == out  # idempotent


def test_config_txt_enables_hardware_watchdog_idempotently() -> None:
    out = hardening.apply_config_txt("[all]\ndtparam=audio=on\n")
    assert "dtparam=watchdog=on" in out
    assert out.count("dtparam=watchdog=on") == 1
    assert hardening.apply_config_txt(out) == out


def test_journald_dropin_is_volatile_and_capped() -> None:
    d = hardening.journald_dropin()
    assert "[Journal]" in d
    assert "Storage=volatile" in d
    assert "RuntimeMaxUse=" in d


def test_fstab_snippet_mounts_persistent_rw_partition() -> None:
    s = hardening.fstab_snippet()
    assert hardening.RW_DIR in s and hardening.RW_DIR == "/var/lib/pibot"
    assert "noatime" in s and "commit=3" in s
    assert "ext4" in s  # not f2fs (research: ext4 survives power loss)


def test_log_upload_points_at_the_mac_over_nebula() -> None:
    # T11.2: ship journald to the Mac's Nebula IP; logs stay volatile locally.
    conf = hardening.render_log_upload("192.168.100.10")
    assert "[Upload]" in conf
    assert "URL=" in conf
    assert "192.168.100.10" in conf  # the Mac's Nebula IP is the sink
    assert str(hardening.JOURNAL_UPLOAD_PORT) in conf
    # local storage is unchanged — log-shipping must not start writing the NVMe
    assert "Storage=volatile" in hardening.journald_dropin()


def test_log_upload_custom_port_and_scheme() -> None:
    conf = hardening.render_log_upload("mac.nebula", port=12345, scheme="https")
    assert "URL=https://mac.nebula:12345" in conf


def test_directives_summary_covers_every_change() -> None:
    summary = hardening.directives()
    blob = "\n".join(summary)
    assert "pcie_aspm=off" in blob
    assert "dtparam=watchdog=on" in blob
    assert "Storage=volatile" in blob
    assert hardening.RW_DIR in blob
    # the systemd watchdog (RuntimeWatchdogSec) belongs to T7.4, not the OS-config layer
    assert "RuntimeWatchdogSec" not in blob
