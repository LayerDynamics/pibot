"""T0.5 — discovery backend wraps tools/pifinder.py without breaking it."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from ipaddress import IPv4Network
from pathlib import Path

from pibot import discovery

REPO_ROOT = Path(__file__).resolve().parent.parent


def _fake_hosts():
    pf = discovery.get_pifinder()
    pi = pf.Host(ip="192.168.1.99", mac="2CCF67386C20", vendor="Raspberry Pi (Trading)")
    pi.is_pi = True
    pi.hostname = "pibot"
    other = pf.Host(ip="192.168.1.1", mac="A840F86544A1")
    return [pi, other]


def test_get_pifinder_exposes_api() -> None:
    pf = discovery.get_pifinder()
    assert hasattr(pf, "discover")
    assert hasattr(pf, "get_local_networks")
    assert hasattr(pf, "DEFAULT_PORTS")
    assert hasattr(pf, "Host")


def test_scan_delegates_to_pifinder(monkeypatch) -> None:
    pf = discovery.get_pifinder()
    hosts = _fake_hosts()
    monkeypatch.setattr(
        pf,
        "get_local_networks",
        lambda: [("en0", IPv4Network("192.168.1.0/24"), "192.168.1.83")],
    )
    seen = {}

    def fake_discover(net, ports, timeout, workers, local_ips):
        seen["net"] = net
        seen["local_ips"] = local_ips
        return hosts

    monkeypatch.setattr(pf, "discover", fake_discover)
    results = discovery.scan()
    assert seen["net"] == IPv4Network("192.168.1.0/24")
    assert "192.168.1.83" in seen["local_ips"]
    assert results == [("192.168.1.0/24", hosts)]


def test_scan_to_json_matches_pifinder_shape(monkeypatch) -> None:
    pf = discovery.get_pifinder()
    hosts = _fake_hosts()
    monkeypatch.setattr(
        pf,
        "get_local_networks",
        lambda: [("en0", IPv4Network("192.168.1.0/24"), "192.168.1.83")],
    )
    monkeypatch.setattr(pf, "discover", lambda *a, **k: hosts)
    payload = discovery.scan_to_json(discovery.scan())
    block = payload["networks"][0]
    assert block["network"] == "192.168.1.0/24"
    assert block["hosts_up"] == 2
    assert block["hosts"] == [asdict(h) for h in hosts]
    assert block["raspberry_pis"] == [asdict(h) for h in hosts if h.is_pi]


def test_discovered_records_only_pis(monkeypatch) -> None:
    pf = discovery.get_pifinder()
    hosts = _fake_hosts()
    monkeypatch.setattr(
        pf,
        "get_local_networks",
        lambda: [("en0", IPv4Network("192.168.1.0/24"), "192.168.1.83")],
    )
    monkeypatch.setattr(pf, "discover", lambda *a, **k: hosts)
    records = discovery.discovered_records(discovery.scan())
    assert len(records) == 1
    rec = records[0]
    assert rec.ip == "192.168.1.99"
    assert rec.pi is True
    assert rec.alias == "pibot"  # derived from hostname
    assert rec.last_seen  # stamped


def test_scan_honors_explicit_cidr(monkeypatch) -> None:
    pf = discovery.get_pifinder()
    monkeypatch.setattr(
        pf,
        "get_local_networks",
        lambda: [("en0", IPv4Network("10.0.0.0/24"), "10.0.0.2")],
    )
    monkeypatch.setattr(pf, "discover", lambda *a, **k: [])
    results = discovery.scan(cidr="192.168.5.0/24")
    assert results[0][0] == "192.168.5.0/24"


def test_pifinder_standalone_still_passes_self_test() -> None:
    # Regression guard: wrapping pifinder must not break the shipped tool.
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "pifinder.py"), "--self-test"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELF-TEST PASSED" in proc.stdout
