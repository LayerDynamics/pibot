"""T12.4.6 — Fine-tune-run registry (SQLite) + serve-checkpoint integration.

Schema:
  finetune_runs(id TEXT PK, dataset TEXT, started REAL, status TEXT,
                checkpoint_out TEXT, served INT)

Status lifecycle: queued → running → done | error
``served`` = 1 when the run's checkpoint_out has been handed to PolicyServerManager.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS finetune_runs (
    id              TEXT PRIMARY KEY,
    dataset         TEXT NOT NULL,
    started         REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    checkpoint_out  TEXT,
    served          INTEGER NOT NULL DEFAULT 0
);
"""

_INSERT = "INSERT INTO finetune_runs (id, dataset, started, status) VALUES (?, ?, ?, ?)"


class FineTuneRegistry:
    """Tracks fine-tune runs and knows how to serve a chosen checkpoint."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(_CREATE_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_run(self, *, dataset: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        self._conn.execute(_INSERT, (run_id, dataset, time.time(), "queued"))
        self._conn.commit()
        return self._get_row(run_id)  # type: ignore[return-value]

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        checkpoint_out: str | None = None,
    ) -> dict[str, Any] | None:
        updates: list[str] = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if checkpoint_out is not None:
            updates.append("checkpoint_out = ?")
            params.append(checkpoint_out)
        if not updates:
            return self._get_row(run_id)
        params.append(run_id)
        self._conn.execute(
            f"UPDATE finetune_runs SET {', '.join(updates)} WHERE id = ?",  # noqa: S608
            params,
        )
        self._conn.commit()
        return self._get_row(run_id)

    def mark_served(self, run_id: str) -> dict[str, Any] | None:
        self._conn.execute("UPDATE finetune_runs SET served = 1 WHERE id = ?", (run_id,))
        self._conn.commit()
        return self._get_row(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, dataset, started, status, checkpoint_out, served "
            "FROM finetune_runs ORDER BY started DESC"
        )
        return [self._row_dict(row) for row in cur]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._get_row(run_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_row(self, run_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT id, dataset, started, status, checkpoint_out, served "
            "FROM finetune_runs WHERE id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        return self._row_dict(row) if row else None

    @staticmethod
    def _row_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": row[0],
            "dataset": row[1],
            "started": row[2],
            "status": row[3],
            "checkpoint_out": row[4],
            "served": bool(row[5]),
        }

    def close(self) -> None:
        self._conn.close()
