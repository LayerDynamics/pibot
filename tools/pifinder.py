#!/usr/bin/env python3
"""pifinder — scan the local network and report which hosts are Raspberry Pis.

The tool auto-detects the local IPv4 subnet(s), sweeps them to discover live
hosts (ICMP ping + TCP probe, which also primes the ARP cache), then harvests
MAC addresses from the ARP table. Each host is scored as a Raspberry Pi using a
union of signals so a Pi is still found even when it sits behind a VPN/overlay
adapter with a locally-administered MAC (no Raspberry Pi OUI):

  * MAC OUI registered to Raspberry Pi (strongest signal)
  * hostname containing "raspberry" / "raspberrypi" / "pi"
  * SSH banner mentioning Raspbian / Raspberry Pi OS / Debian

A Pi reached only over an overlay (no Pi OUI) that also runs a generic OS with
a generic hostname is indistinguishable from any other host by these signals;
re-run with --all to inspect every live host directly.

Discovered Pis are enriched with hostname (reverse DNS, then a best-effort
mDNS lookup via the OS resolver), open TCP ports, and SSH/HTTP service banners.

Pure standard library, no third-party dependencies. Works on macOS and Linux.

Usage:
    python3 pifinder.py                 # auto-detect subnet, list Pis
    python3 pifinder.py --all           # detail every live host, not just Pis
    python3 pifinder.py --cidr 192.168.1.0/24
    python3 pifinder.py --json          # machine-readable output
    python3 pifinder.py --self-test     # run built-in detection checks
"""

from __future__ import annotations

import argparse
import errno
import os
import re
import select
import socket
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Network, ip_address
from platform import system as platform_system
from shutil import which

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# Raspberry Pi MAC-address prefixes, verified against nmap's nmap-mac-prefixes
# database. Stored as upper-case hex with no separators. Note that these are not
# all 24-bit OUIs: F040AF9 is a 28-bit and 8C1F6434A a 36-bit (MA-S) allocation,
# so matching is done by hex-prefix and must respect each prefix's own length.
RASPBERRY_PI_PREFIXES: dict[str, str] = {
    "B827EB": "Raspberry Pi Foundation",
    "DCA632": "Raspberry Pi Trading",
    "E45F01": "Raspberry Pi Trading",
    "28CDC1": "Raspberry Pi Trading",
    "D83ADD": "Raspberry Pi Trading",
    "2CCF67": "Raspberry Pi (Trading)",
    "88A29E": "Raspberry Pi (Trading)",
    "F040AF9": "Raspberry Pi (Trading)",
    "8C1F6434A": "Raspberry Pi (Trading)",
}

# Default TCP ports probed during enrichment. Chosen for relevance to a Pi
# running headless services; UDP-primary ports (53, 5353, 51820) are omitted
# because a TCP connect to them is not meaningful.
DEFAULT_PORTS: list[int] = [
    22,
    80,
    443,
    5900,
    3389,
    8080,
    8000,
    8123,
    1880,
    1883,
    8883,
    3000,
    9090,
    9100,
    631,
    6379,
    5432,
    3306,
    32400,
]

PORT_SERVICE: dict[int, str] = {
    22: "ssh",
    80: "http",
    443: "https",
    5900: "vnc",
    3389: "rdp/xrdp",
    8080: "http-alt",
    8000: "http-alt",
    8123: "home-assistant",
    1880: "node-red",
    1883: "mqtt",
    8883: "mqtt-tls",
    3000: "grafana/node",
    9090: "prometheus",
    9100: "node-exporter",
    631: "cups",
    6379: "redis",
    5432: "postgres",
    3306: "mysql",
    32400: "plex",
}

# Plain-HTTP ports worth grabbing a Server: header from (no TLS handshake).
HTTP_PORTS: tuple[int, ...] = (80, 8080, 8000, 8123, 1880, 3000, 9090, 9100)

# Ports used as a fast liveness probe (host is up if any connects or refuses).
LIVENESS_PORTS: tuple[int, ...] = (22, 80, 443)

IS_MACOS = platform_system() == "Darwin"


# ---------------------------------------------------------------------------
# Host model
# ---------------------------------------------------------------------------


@dataclass
class Host:
    ip: str
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    reachable: bool = False
    latency_ms: float | None = None
    open_ports: list[int] = field(default_factory=list)
    services: dict[str, str] = field(default_factory=dict)
    ssh_banner: str = ""
    http_server: str = ""
    is_pi: bool = False
    confidence: str = ""  # "confirmed" | "likely" | "possible" | ""
    reasons: list[str] = field(default_factory=list)
    is_self: bool = False
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# MAC / OUI helpers
# ---------------------------------------------------------------------------


def normalize_mac(raw: str) -> str:
    """Return a MAC as 12 upper-case hex digits with no separators, or "".

    Handles the macOS `arp` quirk of emitting octets without a leading zero
    (e.g. "ae:2e:91:e:8c:e8" -> "AE2E910E8CE8").
    """
    if not raw:
        return ""
    parts = re.split(r"[:\-]", raw.strip())
    if len(parts) != 6:
        # Some sources emit a bare hex string already; accept 12 hex chars.
        compact = re.sub(r"[^0-9A-Fa-f]", "", raw)
        return compact.upper() if len(compact) == 12 else ""
    out = []
    for p in parts:
        if not re.fullmatch(r"[0-9A-Fa-f]{1,2}", p):
            return ""
        out.append(p.rjust(2, "0"))
    return "".join(out).upper()


def lookup_pi_vendor(mac: str) -> str | None:
    """Return the Raspberry Pi registrant for a MAC, or None if not a Pi OUI."""
    mac_hex = normalize_mac(mac)
    if not mac_hex:
        return None
    for prefix, vendor in RASPBERRY_PI_PREFIXES.items():
        if mac_hex.startswith(prefix):
            return vendor
    return None


# ---------------------------------------------------------------------------
# Local network discovery
# ---------------------------------------------------------------------------


def get_local_networks() -> list[tuple[str, IPv4Network, str]]:
    """Return (iface, network, local_ip) for each active IPv4 interface.

    Parses `ifconfig` (present on both macOS and Linux). Loopback and IPv4
    link-local (169.254/16) addresses are skipped. Falls back to a single
    socket-derived /24 if ifconfig is unavailable or yields nothing usable.
    """
    results: list[tuple[str, IPv4Network, str]] = []
    ifconfig = which("ifconfig")
    if ifconfig:
        try:
            out = subprocess.run([ifconfig], capture_output=True, text=True, timeout=10).stdout
        except (subprocess.SubprocessError, OSError):
            out = ""
        iface = ""
        for line in out.splitlines():
            if line and not line[0].isspace():
                iface = line.split(":", 1)[0].strip()
                continue
            stripped = line.strip()
            if not stripped.startswith("inet "):
                continue
            m_ip = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", stripped)
            if not m_ip:
                continue
            ip = m_ip.group(1)
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            prefix: int | None = None
            m_hex = re.search(r"netmask (0x[0-9a-fA-F]+)", stripped)
            m_dot = re.search(r"netmask (\d+\.\d+\.\d+\.\d+)", stripped)
            if m_hex:
                prefix = bin(int(m_hex.group(1), 16)).count("1")
            elif m_dot:
                prefix = bin(int(ip_address(m_dot.group(1)))).count("1")
            else:
                m_slash = re.search(r"/(\d+)", stripped)
                prefix = int(m_slash.group(1)) if m_slash else 24
            try:
                net = IPv4Network(f"{ip}/{prefix}", strict=False)
            except ValueError:
                continue
            results.append((iface or "?", net, ip))
    if results:
        return results
    # Fallback: derive the primary IP via a routing-table lookup (no packets
    # are sent by connect() on a UDP socket) and assume a /24.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        net = IPv4Network(f"{ip}/24", strict=False)
        return [("?", net, ip)]
    except OSError:
        return []


# ---------------------------------------------------------------------------
# ARP table
# ---------------------------------------------------------------------------

_ARP_LINE = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)")


def read_arp_table() -> dict[str, str]:
    """Return {ip: normalized_mac} from the system ARP cache.

    Uses `arp -a` (its `(ip) at mac` form is identical on macOS and Linux) and
    falls back to /proc/net/arp on Linux. Incomplete entries are skipped.
    """
    table: dict[str, str] = {}
    arp = which("arp")
    if arp:
        try:
            out = subprocess.run(
                [arp, "-a", "-n"], capture_output=True, text=True, timeout=15
            ).stdout
        except (subprocess.SubprocessError, OSError):
            out = ""
        if not out:
            try:
                out = subprocess.run([arp, "-a"], capture_output=True, text=True, timeout=15).stdout
            except (subprocess.SubprocessError, OSError):
                out = ""
        for line in out.splitlines():
            if "incomplete" in line.lower():
                continue
            m = _ARP_LINE.search(line)
            if not m:
                continue
            mac = normalize_mac(m.group(2))
            if mac:
                table[m.group(1)] = mac
    if not table and os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", encoding="utf-8") as fh:
                for line in fh.readlines()[1:]:
                    cols = line.split()
                    if len(cols) >= 4 and cols[3] != "00:00:00:00:00:00":
                        mac = normalize_mac(cols[3])
                        if mac:
                            table[cols[0]] = mac
        except OSError:
            pass
    return table


# ---------------------------------------------------------------------------
# Liveness probing
# ---------------------------------------------------------------------------


def ping(ip: str, timeout: float) -> tuple[bool, float | None]:
    """Send one ICMP echo. Return (replied, round_trip_ms).

    `replied` is True whenever the host answered; `round_trip_ms` may still be
    None if the reply arrived but its time field could not be parsed — that is
    reported as an unknown latency rather than a misleading 0.0.
    """
    if IS_MACOS:
        cmd = ["ping", "-c", "1", "-n", "-W", str(int(timeout * 1000)), ip]
    else:
        secs = max(1, int(timeout + 0.999))
        cmd = ["ping", "-c", "1", "-n", "-W", str(secs), ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
    except (subprocess.SubprocessError, OSError):
        return False, None
    if proc.returncode != 0:
        return False, None
    m = re.search(r"time[=<]\s*([\d.]+)", proc.stdout)
    return True, (float(m.group(1)) if m else None)


def tcp_connect(ip: str, port: int, timeout: float) -> str:
    """Probe one TCP port. Return 'open', 'refused' (host up), or 'down'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        rc = s.connect_ex((ip, port))
    except OSError:
        return "down"
    finally:
        s.close()
    if rc == 0:
        return "open"
    if rc in (errno.ECONNREFUSED, errno.ECONNRESET):
        return "refused"
    return "down"


def measure_latency(ip: str, timeout: float, samples: int = 2) -> float | None:
    """Measure real RTT with a few *serial* pings, returning the minimum.

    The concurrent discovery sweep cannot be trusted for latency: under heavy
    parallelism the reported time is dominated by ping-subprocess scheduling
    delay, not the wire round-trip. This runs after the sweep, one ping at a
    time, so the number reported to the user reflects the actual network.
    """
    best: float | None = None
    for _ in range(max(1, samples)):
        replied, rtt = ping(ip, timeout)
        if replied and rtt is not None:
            best = rtt if best is None else min(best, rtt)
    return best


def probe_liveness(ip: str, timeout: float) -> tuple[bool, list[int]]:
    """Decide whether a host is up. Returns (reachable, open_ports_seen).

    Tries ICMP first; regardless, TCP-probes a few common ports so hosts that
    drop ICMP are still found and the ARP cache is primed. Latency is not
    measured here — it is unreliable under the concurrent sweep and is taken
    serially afterwards by measure_latency().
    """
    reachable = ping(ip, timeout)[0]
    open_seen: list[int] = []
    for port in LIVENESS_PORTS:
        state = tcp_connect(ip, port, timeout)
        if state == "open":
            open_seen.append(port)
            reachable = True
        elif state == "refused":
            reachable = True
    return reachable, open_seen


# ---------------------------------------------------------------------------
# Service enrichment
# ---------------------------------------------------------------------------


def scan_ports(ip: str, ports: Iterable[int], timeout: float, workers: int) -> list[int]:
    """Return the sorted list of open TCP ports for a host."""
    ports = list(ports)
    if not ports:
        return []
    found: list[int] = []
    with ThreadPoolExecutor(max_workers=min(workers, len(ports))) as pool:
        futures = {pool.submit(tcp_connect, ip, p, timeout): p for p in ports}
        for fut in as_completed(futures):
            if fut.result() == "open":
                found.append(futures[fut])
    return sorted(found)


def grab_ssh_banner(ip: str, timeout: float) -> str:
    """Read the SSH identification string the server sends on connect."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        if s.connect_ex((ip, 22)) != 0:
            return ""
        data = s.recv(256)
    except OSError:
        return ""
    finally:
        s.close()
    line = data.decode("utf-8", "replace").splitlines()[0:1]
    return line[0].strip() if line else ""


def grab_http_server(ip: str, port: int, timeout: float) -> str:
    """Return the value of the HTTP Server: response header, or ""."""
    request = (
        f"HEAD / HTTP/1.0\r\nHost: {ip}\r\nUser-Agent: pifinder/1.0\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        if s.connect_ex((ip, port)) != 0:
            return ""
        s.sendall(request)
        chunks = []
        while len(b"".join(chunks)) < 4096:
            chunk = s.recv(1024)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError:
        return ""
    finally:
        s.close()
    text = b"".join(chunks).decode("utf-8", "replace")
    for line in text.splitlines():
        if line.lower().startswith("server:"):
            return line.split(":", 1)[1].strip()
    return ""


def _read_stream_until(cmd: list[str], timeout: float, stop_markers: Iterable[bytes]) -> str:
    """Run a long-lived command, collect stdout up to `timeout`, then stop it.

    Returns as soon as any byte sequence in `stop_markers` appears, so a fast
    negative answer does not cost the full timeout.
    """
    markers = list(stop_markers)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return ""
    assert proc.stdout is not None
    fd = proc.stdout.fileno()
    buf = b""
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                break
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf += chunk
            if any(marker in buf for marker in markers):
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
    return buf.decode("utf-8", "replace")


def _parse_dns_sd_ptr(out: str) -> str:
    """Extract a hostname from `dns-sd -Q ... PTR` output, ignoring misses.

    A hit looks like `... <query>. PTR IN <hostname>.`; a miss looks like
    `... PTR IN 0.0.0.0 No Such Record`. The answer is the Rdata column, i.e.
    the token immediately after the `IN` class field.
    """
    for line in out.splitlines():
        if " PTR " not in line or "No Such Record" in line:
            continue
        tokens = line.split()
        if "IN" not in tokens:
            continue
        idx = tokens.index("IN")
        if idx + 1 >= len(tokens):
            continue
        rdata = tokens[idx + 1].rstrip(".")
        if rdata and rdata != "0.0.0.0" and not rdata.endswith("in-addr.arpa"):
            return rdata
    return ""


def mdns_reverse(ip: str, timeout: float) -> str:
    """Best-effort hostname via the OS mDNS resolver (dns-sd / avahi)."""
    if IS_MACOS and which("dns-sd"):
        reverse = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
        out = _read_stream_until(
            ["dns-sd", "-Q", reverse, "PTR"],
            timeout,
            stop_markers=[b".local.", b"No Such Record"],
        )
        return _parse_dns_sd_ptr(out)
    resolver = which("avahi-resolve-address")
    if resolver:
        try:
            out = subprocess.run(
                [resolver, ip], capture_output=True, text=True, timeout=timeout + 1
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return ""
        cols = out.split()
        return cols[1].rstrip(".") if len(cols) >= 2 else ""
    return ""


def resolve_hostname(ip: str, timeout: float) -> str:
    """Reverse-resolve `ip`, falling back to an mDNS query when DNS is silent."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        pass
    return mdns_reverse(ip, timeout)


# ---------------------------------------------------------------------------
# Raspberry Pi scoring
# ---------------------------------------------------------------------------


def score_pi(host: Host) -> None:
    """Populate host.is_pi / confidence / reasons from all available signals."""
    reasons: list[str] = []
    confidence = ""

    vendor = lookup_pi_vendor(host.mac)
    if vendor:
        host.vendor = vendor
        reasons.append(f"MAC OUI registered to {vendor}")
        confidence = "confirmed"

    name = host.hostname.lower()
    if name and ("raspberrypi" in name or "raspberry" in name):
        reasons.append(f"hostname '{host.hostname}' identifies a Raspberry Pi")
        confidence = "confirmed"
    elif re.search(r"(^|[.\-_])pi([.\-_]|$)", name):
        reasons.append(f"hostname '{host.hostname}' suggests a Pi")
        confidence = confidence or "likely"

    banner = host.ssh_banner.lower()
    if banner:
        if "raspbian" in banner or "raspberry" in banner:
            reasons.append(f"SSH banner reports Raspberry Pi OS: {host.ssh_banner}")
            confidence = "confirmed"
        elif "debian" in banner:
            reasons.append(f"SSH banner reports Debian (Pi OS base): {host.ssh_banner}")
            confidence = confidence or "likely"

    host.reasons = reasons
    host.is_pi = bool(reasons)
    host.confidence = confidence if host.is_pi else ""


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def discover(
    network: IPv4Network,
    ports: list[int],
    timeout: float,
    workers: int,
    local_ips: Iterable[str],
) -> list[Host]:
    """Run the full discovery + enrichment pipeline for one network."""
    local_ips = set(local_ips)
    targets = [str(ip) for ip in network.hosts()]

    # 1. Liveness sweep (also primes the ARP cache). The sweep's own latency is
    #    discarded — only liveness and the incidentally-open ports are kept,
    #    because RTT under this concurrency is scheduling noise (re-measured
    #    serially in step 3).
    live: dict[str, list[int]] = {}
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(targets)))) as pool:
        futures = {pool.submit(probe_liveness, ip, timeout): ip for ip in targets}
        for fut in as_completed(futures):
            ip = futures[fut]
            reachable, open_seen = fut.result()
            if reachable:
                live[ip] = open_seen

    # 2. Harvest MACs from the now-populated ARP cache. Include ARP-only hosts
    #    that live inside the target network even if they ignored our probes.
    arp = read_arp_table()
    for ip, mac in arp.items():
        try:
            if ip_address(ip) in network and ip not in live and mac:
                live[ip] = []
        except ValueError:
            continue

    if not live:
        return []

    hosts: dict[str, Host] = {}
    for ip, open_seen in live.items():
        h = Host(ip=ip, reachable=True)
        h.mac = arp.get(ip, "")
        if open_seen:
            h.open_ports = sorted(open_seen)
        if ip in local_ips:
            h.is_self = True
        hosts[ip] = h

    host_list = list(hosts.values())

    # 3. Re-measure latency serially so the reported RTT is real, not the
    #    scheduling delay seen under the concurrent sweep above. The serial
    #    result is authoritative for the "no ICMP reply" note as well.
    for h in host_list:
        h.latency_ms = measure_latency(h.ip, timeout)
        if h.latency_ms is None and not h.is_self:
            h.notes.append("seen via ARP/TCP only (no ICMP reply)")

    # 4. Concurrent hostname resolution.
    with ThreadPoolExecutor(max_workers=min(workers, len(host_list))) as pool:
        futures = {pool.submit(resolve_hostname, h.ip, timeout): h for h in host_list}
        for fut in as_completed(futures):
            futures[fut].hostname = fut.result() or ""

    # 5. Concurrent full port scan.
    with ThreadPoolExecutor(max_workers=min(workers, len(host_list))) as pool:
        futures = {pool.submit(scan_ports, h.ip, ports, timeout, workers): h for h in host_list}
        for fut in as_completed(futures):
            h = futures[fut]
            opened = set(h.open_ports) | set(fut.result())
            h.open_ports = sorted(opened)
            h.services = {str(p): PORT_SERVICE.get(p, "unknown") for p in h.open_ports}

    # 6. Concurrent banner grabs (SSH + first plaintext HTTP port).
    def grab(h: Host) -> None:
        if 22 in h.open_ports:
            h.ssh_banner = grab_ssh_banner(h.ip, timeout)
        for port in HTTP_PORTS:
            if port in h.open_ports:
                server = grab_http_server(h.ip, port, timeout)
                if server:
                    h.http_server = f"{server} (port {port})"
                    break

    with ThreadPoolExecutor(max_workers=min(workers, len(host_list))) as pool:
        list(pool.map(grab, host_list))

    # 7. Score each host as a Raspberry Pi.
    for h in host_list:
        score_pi(h)

    host_list.sort(key=lambda h: tuple(int(o) for o in h.ip.split(".")))
    return host_list


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _fmt_latency(host: Host) -> str:
    if host.latency_ms is None:
        return "-"
    return f"{host.latency_ms:.1f}ms"


def print_summary_table(hosts: list[Host]) -> None:
    headers = ["IP", "MAC", "Pi?", "Vendor / OS hint", "Hostname", "RTT"]
    rows: list[list[str]] = []
    for h in hosts:
        pi_flag = "PI" if h.is_pi else ""
        hint = h.vendor or (h.ssh_banner[:28] if h.ssh_banner else "")
        name = h.hostname + (" (this host)" if h.is_self else "")
        rows.append([h.ip, h.mac or "-", pi_flag, hint or "-", name or "-", _fmt_latency(h)])
    widths = [len(x) for x in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def print_host_detail(host: Host) -> None:
    title = f"  Raspberry Pi @ {host.ip}" if host.is_pi else f"  Host @ {host.ip}"
    print()
    print(title)
    print("  " + "-" * (len(title) - 2))
    if host.is_pi:
        print(f"  Detection : {host.confidence}")
        for reason in host.reasons:
            print(f"            - {reason}")
    if host.hostname:
        print(f"  Hostname  : {host.hostname}")
    if host.mac:
        vendor = host.vendor or "unknown vendor"
        print(f"  MAC       : {host.mac}  ({vendor})")
    if host.latency_ms is not None:
        print(f"  Latency   : {host.latency_ms:.1f} ms")
    if host.open_ports:
        svc = ", ".join(f"{p}/{PORT_SERVICE.get(p, 'unknown')}" for p in host.open_ports)
        print(f"  Open ports: {svc}")
    else:
        print("  Open ports: none of the scanned ports were open")
    if host.ssh_banner:
        print(f"  SSH       : {host.ssh_banner}")
    if host.http_server:
        print(f"  HTTP      : {host.http_server}")
    if 22 in host.open_ports:
        target = host.hostname or host.ip
        banner = host.ssh_banner.lower()
        if "ubuntu" in banner:
            print(f"  Connect   : ssh ubuntu@{target}   (banner reports Ubuntu)")
        elif "raspbian" in banner or (host.is_pi and "debian" in banner):
            print(f"  Connect   : ssh pi@{target}   (Raspberry Pi OS default user)")
        else:
            print(f"  Connect   : ssh <user>@{target}")
    for note in host.notes:
        print(f"  Note      : {note}")


def render(hosts: list[Host], show_all: bool, as_json: bool, network_label: str) -> None:
    if as_json:
        import json

        payload = {
            "network": network_label,
            "hosts_up": len(hosts),
            "raspberry_pis": [asdict(h) for h in hosts if h.is_pi],
            "hosts": [asdict(h) for h in hosts],
        }
        print(json.dumps(payload, indent=2))
        return

    pis = [h for h in hosts if h.is_pi]
    print(
        f"\nScanned {network_label}: {len(hosts)} host(s) up, "
        f"{len(pis)} Raspberry Pi(s) identified.\n"
    )
    if hosts:
        print_summary_table(hosts)

    detail = hosts if show_all else pis
    if detail:
        print("\n" + "=" * 60)
        for h in detail:
            print_host_detail(h)
    elif not pis:
        print("\nNo Raspberry Pi identified on this network.")
        print("If your Pi is reachable only over a VPN/overlay (e.g. ZeroTier),")
        print("it may show a non-Pi MAC above — re-run with --all to inspect every host.")


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def self_test() -> int:
    """Exercise the detection logic that real scans rarely get to prove."""
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        status = "ok  " if cond else "FAIL"
        print(f"  [{status}] {name}")
        if not cond:
            failures.append(name)

    # MAC normalization, including the macOS single-digit-octet quirk.
    check("normalize pads single-digit octets", normalize_mac("b8:27:eb:1:2:3") == "B827EB010203")
    check("normalize handles dashes", normalize_mac("dc-a6-32-aa-bb-cc") == "DCA632AABBCC")
    check("normalize rejects junk", normalize_mac("not-a-mac") == "")
    check("normalize accepts bare 12-hex", normalize_mac("b827ebaabbcc") == "B827EBAABBCC")

    # OUI matching across 24-bit, 28-bit and 36-bit allocations.
    check(
        "Pi Foundation OUI matched",
        lookup_pi_vendor("b8:27:eb:1:2:3") == "Raspberry Pi Foundation",
    )
    check("Pi 5 OUI matched", lookup_pi_vendor("2c:cf:67:aa:bb:cc") == "Raspberry Pi (Trading)")
    check("28-bit MA-M prefix matched", lookup_pi_vendor("f0:40:af:9a:bb:cc") is not None)
    check("28-bit prefix not over-matched", lookup_pi_vendor("f0:40:af:0a:bb:cc") is None)
    check("non-Pi OUI rejected", lookup_pi_vendor("ae:8a:23:e4:11:6f") is None)
    check("empty MAC rejected", lookup_pi_vendor("") is None)

    # dns-sd PTR parsing: a miss must not leak the "No Such Record" tokens.
    miss = (
        "Timestamp     A/R  Flags  IF  Name  Type Class Rdata\n"
        " 9:19:18.680  Add  2  0  99.1.168.192.in-addr.arpa.    PTR    IN     "
        "0.0.0.0    No Such Record"
    )
    check("dns-sd miss yields empty hostname", _parse_dns_sd_ptr(miss) == "")
    hit = " 9:19:18.680  Add  2  11  42.1.168.192.in-addr.arpa.    PTR    IN     raspberrypi.local."
    check("dns-sd hit yields hostname", _parse_dns_sd_ptr(hit) == "raspberrypi.local")

    # Scoring: each independent signal must flag a Pi.
    h_oui = Host(ip="0.0.0.1", mac="b8:27:eb:01:02:03")
    score_pi(h_oui)
    check("OUI alone confirms Pi", h_oui.is_pi and h_oui.confidence == "confirmed")

    h_name = Host(ip="0.0.0.2", hostname="raspberrypi.local")
    score_pi(h_name)
    check("hostname alone confirms Pi (overlay case)", h_name.is_pi)

    h_banner = Host(ip="0.0.0.3", ssh_banner="SSH-2.0-OpenSSH_9.2p1 Raspbian-2", open_ports=[22])
    score_pi(h_banner)
    check("SSH banner alone confirms Pi", h_banner.is_pi and h_banner.confidence == "confirmed")

    h_none = Host(ip="0.0.0.4", mac="ae:8a:23:e4:11:6f", hostname="router", ssh_banner="")
    score_pi(h_none)
    check("ordinary host not flagged", not h_none.is_pi)

    print()
    if failures:
        print(f"SELF-TEST FAILED: {len(failures)} check(s) failed.")
        return 1
    print("SELF-TEST PASSED: all checks green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_ports(spec: str) -> list[int]:
    ports: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            ports.extend(range(int(lo), int(hi) + 1))
        else:
            ports.append(int(part))
    return sorted({p for p in ports if 0 < p < 65536})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan the local network and report Raspberry Pi hosts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cidr",
        help="network to scan, e.g. 192.168.1.0/24 (default: auto-detect every local subnet)",
    )
    parser.add_argument(
        "--all", action="store_true", help="show detail for every live host, not just Pis"
    )
    parser.add_argument(
        "--ports",
        default=",".join(str(p) for p in DEFAULT_PORTS),
        help="comma/range list of TCP ports to scan",
    )
    parser.add_argument("--timeout", type=float, default=1.0, help="per-probe timeout in seconds")
    parser.add_argument("--workers", type=int, default=128, help="maximum concurrent probes")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--force", action="store_true", help="allow scanning networks larger than 4096 addresses"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in detection checks and exit"
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        ports = parse_ports(args.ports)
    except ValueError:
        parser.error(f"invalid --ports value: {args.ports!r}")
    if not ports:
        parser.error("no valid ports to scan")

    local_nets = get_local_networks()
    local_ips = [ip for _, _, ip in local_nets]

    if args.cidr:
        try:
            networks = [IPv4Network(args.cidr, strict=False)]
        except ValueError as exc:
            parser.error(f"invalid --cidr: {exc}")
    else:
        networks = []
        seen = set()
        for _, net, _ in local_nets:
            if net.compressed not in seen:
                seen.add(net.compressed)
                networks.append(net)
        if not networks:
            print(
                "Could not determine the local network. Pass one explicitly with --cidr.",
                file=sys.stderr,
            )
            return 2

    exit_code = 0
    for net in networks:
        if net.num_addresses > 4096 and not args.force:
            print(
                f"Refusing to scan {net} ({net.num_addresses} addresses) without --force.",
                file=sys.stderr,
            )
            exit_code = 2
            continue
        if not args.json:
            print(f"Sweeping {net} ...", file=sys.stderr)
        start = time.monotonic()
        hosts = discover(net, ports, args.timeout, args.workers, local_ips)
        elapsed = time.monotonic() - start
        render(hosts, args.all, args.json, net.compressed)
        if not args.json:
            print(f"\n(done in {elapsed:.1f}s)", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
