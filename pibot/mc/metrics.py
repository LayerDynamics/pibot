"""MetricsStore — SQLite time-series for telemetry samples (SPEC-3 §3.3, T12.4.1).

Schema (one row per telemetry snapshot):
  telemetry(ts REAL, robot TEXT, temp_c REAL, battery_v REAL, estop INT,
            transport_open INT, policy_connected INT, last_infer_ms REAL,
            chunk_age_ms REAL, raw JSON)

Writes are buffered in a list and flushed in batches (``FLUSH_SIZE``).  The caller
is never blocked by SQLite I/O — ``write()`` only appends to the buffer; ``flush()``
materialises the batch.  ``prune()`` enforces ``MAX_AGE_DAYS`` and ``MAX_ROWS`` caps.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

MAX_AGE_DAYS: int = 30
MAX_ROWS: int = 100_000
FLUSH_SIZE: int = 50

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS telemetry (
    ts              REAL    NOT NULL,
    robot           TEXT,
    temp_c          REAL,
    battery_v       REAL,
    estop           INTEGER,
    transport_open  INTEGER,
    policy_connected INTEGER,
    last_infer_ms   REAL,
    chunk_age_ms    REAL,
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS telemetry_ts ON telemetry(ts);
"""

_INSERT_SQL = """
INSERT INTO telemetry
    (ts, robot, temp_c, battery_v, estop, transport_open,
     policy_connected, last_infer_ms, chunk_age_ms, raw)
VALUES
    (:ts, :robot, :temp_c, :battery_v, :estop, :transport_open,
     :policy_connected, :last_infer_ms, :chunk_age_ms, :raw)
"""

_VALID_COLS = frozenset(
    {
        "ts",
        "robot",
        "temp_c",
        "battery_v",
        "estop",
        "transport_open",
        "policy_connected",
        "last_infer_ms",
        "chunk_age_ms",
        "raw",
    }
)


class MetricsStore:
    """Buffered SQLite telemetry time-series store."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        *,
        flush_size: int = FLUSH_SIZE,
    ) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()
        self._buf: list[dict[str, Any]] = []
        self._flush_size = flush_size

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def write(self, snapshot: dict[str, Any], *, robot: str | None = None) -> None:
        """Buffer a telemetry snapshot for batch insertion. Non-blocking."""
        pi = snapshot.get("pi") or {}
        safety = snapshot.get("safety") or {}
        transport = snapshot.get("transport") or {}
        policy = snapshot.get("policy") or {}
        robot_data = snapshot.get("robot") or {}

        self._buf.append(
            {
                "ts": float(snapshot.get("ts") or time.time()),
                "robot": robot,
                "temp_c": pi.get("temp_c"),
                "battery_v": (robot_data.get("battery") or {}).get("volts"),
                "estop": int(bool(safety.get("estop"))),
                "transport_open": int(bool(transport.get("open"))),
                "policy_connected": int(bool(policy.get("connected"))),
                "last_infer_ms": policy.get("last_inference_ms"),
                "chunk_age_ms": policy.get("chunk_age_ms"),
                "raw": json.dumps(snapshot),
            }
        )
        if len(self._buf) >= self._flush_size:
            self._flush()

    def flush(self) -> None:
        """Materialise any buffered rows into SQLite."""
        self._flush()

    def _flush(self) -> None:
        if not self._buf:
            return
        rows, self._buf = self._buf[:], []
        self._conn.executemany(_INSERT_SQL, rows)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query / export
    # ------------------------------------------------------------------

    def query(
        self,
        from_ts: float,
        to_ts: float,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return rows in [from_ts, to_ts], ordered by ts."""
        self._flush()
        cols = ", ".join(f for f in (fields or []) if f in _VALID_COLS) or "*"
        cur = self._conn.execute(
            f"SELECT {cols} FROM telemetry WHERE ts >= ? AND ts <= ? ORDER BY ts",  # noqa: S608
            (from_ts, to_ts),
        )
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]

    def export(self, from_ts: float, to_ts: float, fmt: str = "json") -> str:
        """Return all rows in [from_ts, to_ts] as a CSV or JSON string."""
        rows = self.query(from_ts, to_ts)
        if fmt == "csv":
            if not rows:
                return ""
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            return buf.getvalue()
        return json.dumps(rows)

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def prune(self) -> int:
        """Delete rows beyond MAX_AGE_DAYS / MAX_ROWS caps. Returns rows deleted."""
        self._flush()
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        cur = self._conn.execute("DELETE FROM telemetry WHERE ts < ?", (cutoff,))
        deleted = cur.rowcount

        total: int = self._conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
        if total > MAX_ROWS:
            excess = total - MAX_ROWS
            self._conn.execute(
                "DELETE FROM telemetry WHERE rowid IN "
                "(SELECT rowid FROM telemetry ORDER BY ts ASC LIMIT ?)",
                (excess,),
            )
            deleted += excess

        self._conn.commit()
        return deleted

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the number of persisted rows (after flushing the buffer)."""
        self._flush()
        return self._conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]

    def close(self) -> None:
        self._flush()
        self._conn.close()
