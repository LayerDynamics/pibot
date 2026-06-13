"""T12.4.3 — Session recorder + replay (SPEC-3 §3.3 / FR-14).

Schema:
  sessions(id TEXT PK, robot TEXT, started REAL, ended REAL)
  session_events(session_id TEXT, ts REAL, kind TEXT, data TEXT/JSON)

``SessionRecorder`` tracks the active recording session and accumulates events.
The replay bundle is { session, events, telemetry_window } — the telemetry window is
the (started, ended) pair that the caller can pass to MetricsStore.query().
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id      TEXT    PRIMARY KEY,
    robot   TEXT,
    started REAL    NOT NULL,
    ended   REAL
);
CREATE TABLE IF NOT EXISTS session_events (
    session_id  TEXT    NOT NULL REFERENCES sessions(id),
    ts          REAL    NOT NULL,
    kind        TEXT    NOT NULL,
    data        TEXT
);
CREATE INDEX IF NOT EXISTS session_events_sid ON session_events(session_id, ts);
"""

_INSERT_SESSION = "INSERT INTO sessions (id, robot, started) VALUES (?, ?, ?)"
_END_SESSION = "UPDATE sessions SET ended = ? WHERE id = ?"
_INSERT_EVENT = "INSERT INTO session_events (session_id, ts, kind, data) VALUES (?, ?, ?, ?)"


class SessionRecorder:
    """Records telemetry + control events during a bounded session."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()
        self._active_id: str | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self, *, robot: str | None = None) -> str:
        """Open a new recording session. Returns the new session id."""
        if self._active_id is not None:
            self.stop()
        sid = str(uuid.uuid4())
        self._conn.execute(_INSERT_SESSION, (sid, robot, time.time()))
        self._conn.commit()
        self._active_id = sid
        return sid

    def stop(self) -> dict[str, Any]:
        """Finalize the active session. Returns the session record."""
        if self._active_id is None:
            raise RuntimeError("no active session")
        sid = self._active_id
        self._active_id = None
        now = time.time()
        self._conn.execute(_END_SESSION, (now, sid))
        self._conn.commit()
        return self._session_row(sid)  # type: ignore[return-value]

    @property
    def active_id(self) -> str | None:
        return self._active_id

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def add_event(
        self,
        *,
        session_id: str | None = None,
        kind: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record a discrete event into a session (defaults to the active session)."""
        sid = session_id or self._active_id
        if sid is None:
            return
        self._conn.execute(
            _INSERT_EVENT,
            (sid, time.time(), kind, json.dumps(data) if data is not None else None),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_sessions(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, robot, started, ended FROM sessions ORDER BY started DESC"
        )
        return [dict(zip(("id", "robot", "started", "ended"), row, strict=False)) for row in cur]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._session_row(session_id)
        if row is None:
            return None
        events = self._events(session_id)
        return {
            **row,
            "events": events,
            "telemetry_window": {
                "from": row["started"],
                "to": row["ended"] or time.time(),
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_row(self, sid: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT id, robot, started, ended FROM sessions WHERE id = ?", (sid,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip(("id", "robot", "started", "ended"), row, strict=False))

    def _events(self, sid: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT ts, kind, data FROM session_events WHERE session_id = ? ORDER BY ts",
            (sid,),
        )
        out = []
        for ts, kind, data in cur:
            out.append(
                {
                    "ts": ts,
                    "kind": kind,
                    "data": json.loads(data) if data else None,
                }
            )
        return out

    def close(self) -> None:
        self._conn.close()
