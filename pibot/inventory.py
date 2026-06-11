"""Host inventory and target resolution for the PiBot Control Suite.

Known robots are persisted to ``$PIBOT_CONFIG_DIR/inventory.toml`` so an operator can
refer to a robot by a friendly alias (``pibot``) instead of an IP that may change.
Records are flat scalars; the full pluggable-transport parameters live Pi-side in
``robot/config/transport.toml`` (SPEC-1 §6.2), so the inventory only records the
backend *name* it was last reached over.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from ipaddress import AddressValueError, IPv4Address
from pathlib import Path

from pibot import tomlio
from pibot.config import config_dir
from pibot.errors import InventoryError
from pibot.logging import get_logger

_log = get_logger("inventory")
_INVENTORY_VERSION = 1


@dataclass
class InventoryRecord:
    """One known robot."""

    alias: str
    ip: str = ""
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    user: str | None = None
    link: str = ""
    pi: bool = False
    last_seen: str = ""

    @property
    def address(self) -> str:
        """The best address to connect to: explicit IP, else hostname."""
        return self.ip or self.hostname


class Inventory:
    """A mutable collection of :class:`InventoryRecord`, persisted to TOML."""

    def __init__(self, records: list[InventoryRecord] | None = None, path: Path | None = None):
        self._records: dict[str, InventoryRecord] = {}
        for rec in records or []:
            self._records[rec.alias] = rec
        self._path = path or (config_dir() / "inventory.toml")

    # ---- persistence -----------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> Inventory:
        """Load the inventory, tolerating (and skipping) malformed records."""
        target = Path(path) if path is not None else config_dir() / "inventory.toml"
        data = tomlio.load(target)
        known = {f.name for f in fields(InventoryRecord)}
        records: list[InventoryRecord] = []
        for raw in data.get("host", []):
            alias = raw.get("alias")
            if not alias:
                _log.warning("skipping inventory record without an alias: %r", raw)
                continue
            clean = {k: v for k, v in raw.items() if k in known}
            records.append(InventoryRecord(**clean))
        return cls(records, target)

    def save(self) -> None:
        """Write the inventory to disk (creating the config dir if needed)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _INVENTORY_VERSION,
            "host": [self._record_dict(rec) for rec in self._records.values()],
        }
        tomlio.dump(payload, self._path)

    @staticmethod
    def _record_dict(rec: InventoryRecord) -> dict[str, object]:
        # Drop None (user) so tomlio omits it cleanly.
        return {k: v for k, v in asdict(rec).items() if v is not None}

    # ---- CRUD ------------------------------------------------------------

    def add(self, record: InventoryRecord) -> None:
        """Insert or replace the record for ``record.alias`` (upsert)."""
        self._records[record.alias] = record

    def get(self, alias: str) -> InventoryRecord | None:
        return self._records.get(alias)

    def list(self) -> list[InventoryRecord]:
        return list(self._records.values())

    def remove(self, alias: str) -> None:
        if alias not in self._records:
            raise InventoryError(f"no inventory entry aliased {alias!r}")
        del self._records[alias]

    def set_alias(self, old: str, new: str) -> None:
        if old not in self._records:
            raise InventoryError(f"no inventory entry aliased {old!r}")
        record = self._records.pop(old)
        record.alias = new
        self._records[new] = record

    # ---- resolution ------------------------------------------------------

    def resolve(self, target: str) -> str:
        """Resolve a target to a connectable address.

        Order (SPEC-1 FR-1.3): known alias → raw IPv4 → ``.local``/qualified name →
        bare name promoted to mDNS ``<name>.local``.
        """
        target = (target or "").strip()
        if not target:
            raise InventoryError("empty target")
        if target in self._records:
            address = self._records[target].address
            if not address:
                raise InventoryError(f"inventory entry {target!r} has no ip or hostname")
            return address
        if _is_ipv4(target):
            return target
        if "." in target:
            return target
        return f"{target}.local"


def _is_ipv4(value: str) -> bool:
    try:
        IPv4Address(value)
        return True
    except AddressValueError:
        return False
