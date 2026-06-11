"""Discovery backend — wraps the shipped ``tools/pifinder.py`` network scanner.

``pifinder.py`` is a standalone, dependency-free tool and must keep working when run
directly. Rather than move or repackage it, this module loads it by file path and
exposes a thin façade so ``pibot discover`` reuses the exact same scan logic (and the
same JSON shape), and discovered Raspberry Pis can be folded into the inventory.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from ipaddress import IPv4Network
from pathlib import Path
from types import ModuleType
from typing import Any

from pibot.errors import PibotError
from pibot.inventory import InventoryRecord

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PIFINDER_PATH = _REPO_ROOT / "tools" / "pifinder.py"

_pifinder: ModuleType | None = None

# (network_label, list[pifinder.Host])
NetworkResult = tuple[str, list[Any]]


def get_pifinder() -> ModuleType:
    """Load (once) and return the pifinder module object."""
    global _pifinder
    if _pifinder is None:
        spec = importlib.util.spec_from_file_location("pifinder", _PIFINDER_PATH)
        if spec is None or spec.loader is None:
            raise PibotError(f"cannot load pifinder from {_PIFINDER_PATH}")
        module = importlib.util.module_from_spec(spec)
        # Register before exec: dataclasses resolves the generated __init__'s globals
        # via sys.modules[cls.__module__], which fails if pifinder isn't present yet.
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _pifinder = module
    return _pifinder


def scan(
    cidr: str | None = None,
    *,
    timeout: float = 1.0,
    workers: int = 128,
) -> list[NetworkResult]:
    """Scan one explicit CIDR or every auto-detected local subnet.

    Returns a list of ``(network_label, hosts)`` where ``hosts`` are pifinder ``Host``
    objects — the same objects the standalone tool produces.
    """
    pf = get_pifinder()
    locals_ = pf.get_local_networks()
    local_ips = [ip for _, _, ip in locals_]

    if cidr:
        networks = [IPv4Network(cidr, strict=False)]
    else:
        seen: set[str] = set()
        networks = []
        for _, net, _ in locals_:
            if net.compressed not in seen:
                seen.add(net.compressed)
                networks.append(net)

    ports = pf.DEFAULT_PORTS
    results: list[NetworkResult] = []
    for net in networks:
        hosts = pf.discover(net, ports, timeout, workers, local_ips)
        results.append((net.compressed, hosts))
    return results


def scan_to_json(results: list[NetworkResult]) -> dict[str, Any]:
    """Render scan results to the same per-network JSON shape pifinder emits."""
    networks = []
    for label, hosts in results:
        networks.append(
            {
                "network": label,
                "hosts_up": len(hosts),
                "raspberry_pis": [asdict(h) for h in hosts if h.is_pi],
                "hosts": [asdict(h) for h in hosts],
            }
        )
    return {"networks": networks}


def discovered_records(results: list[NetworkResult]) -> list[InventoryRecord]:
    """Convert the Raspberry Pis found in a scan into inventory records."""
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    records: list[InventoryRecord] = []
    for _, hosts in results:
        for host in hosts:
            if not host.is_pi:
                continue
            records.append(
                InventoryRecord(
                    alias=_alias_for(host),
                    ip=host.ip,
                    mac=host.mac,
                    vendor=host.vendor,
                    hostname=host.hostname,
                    pi=True,
                    last_seen=stamp,
                )
            )
    return records


def _alias_for(host: Any) -> str:
    if host.hostname:
        return host.hostname.split(".")[0]
    if host.mac:
        return f"pi-{host.mac[-4:].lower()}"
    return "pi-" + host.ip.replace(".", "-")
