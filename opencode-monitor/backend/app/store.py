"""SQLite store (stdlib sqlite3 only). Tables: projects / sessions / sync_state."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT,
    path TEXT,
    raw TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT,
    updated_at TEXT,
    raw TEXT,
    synced_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    old_updated_at TEXT,
    new_updated_at TEXT,
    detected_at TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_transitions_session ON transitions(session_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_transitions_detected ON transitions(detected_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_project(
    conn: sqlite3.Connection,
    project_id: str,
    name: Optional[str] = None,
    path: Optional[str] = None,
    raw: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO projects (id, name, path, raw, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            path=excluded.path,
            raw=excluded.raw,
            updated_at=excluded.updated_at
        """,
        (
            project_id,
            name,
            path,
            json.dumps(raw, ensure_ascii=False) if raw is not None else None,
            _now(),
        ),
    )


def upsert_session(
    conn: sqlite3.Connection,
    session_id: str,
    project_id: Optional[str] = None,
    title: Optional[str] = None,
    updated_at: Optional[str] = None,
    raw: Optional[dict] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO sessions (id, project_id, title, updated_at, raw, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            project_id=excluded.project_id,
            title=excluded.title,
            updated_at=excluded.updated_at,
            raw=excluded.raw,
            synced_at=excluded.synced_at
        """,
        (
            session_id,
            project_id,
            title,
            updated_at,
            json.dumps(raw, ensure_ascii=False) if raw is not None else None,
            _now(),
        ),
    )


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, path, raw, updated_at FROM projects ORDER BY updated_at DESC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def list_sessions(
    conn: sqlite3.Connection, project_id: Optional[str] = None, limit: int = 200
) -> list[dict[str, Any]]:
    if project_id:
        rows = conn.execute(
            "SELECT id, project_id, title, updated_at, raw, synced_at"
            " FROM sessions WHERE project_id = ? ORDER BY updated_at DESC, id ASC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, project_id, title, updated_at, raw, synced_at"
            " FROM sessions ORDER BY updated_at DESC, id ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def count_projects(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()
    return int(row["n"])


def count_sessions(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
    return int(row["n"])


def get_sync_state(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_sync_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (key, value, _now()),
    )


# --- P3: completion transitions -------------------------------------------

TRANSITION_KINDS = ("created", "updated", "finished", "anomaly")


def insert_transition(
    conn: sqlite3.Connection,
    session_id: str,
    kind: str,
    old_updated_at: Optional[str] = None,
    new_updated_at: Optional[str] = None,
    detail: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO transitions (session_id, kind, old_updated_at, new_updated_at, detected_at, detail)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, kind, old_updated_at, new_updated_at, _now(), detail),
    )
    return int(cur.lastrowid)


def list_transitions(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, session_id, kind, old_updated_at, new_updated_at, detected_at, detail"
        " FROM transitions ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def search_transitions(
    conn: sqlite3.Connection,
    session_id: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conds: list[str] = []
    args: list[Any] = []
    if session_id:
        conds.append("session_id = ?")
        args.append(session_id)
    if kind:
        conds.append("kind = ?")
        args.append(kind)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    args.append(limit)
    rows = conn.execute(
        "SELECT id, session_id, kind, old_updated_at, new_updated_at, detected_at, detail"
        f" FROM transitions {where} ORDER BY id DESC LIMIT ?",
        tuple(args),
    ).fetchall()
    return [dict(r) for r in rows]


def list_history(
    conn: sqlite3.Connection, session_id: str, limit: int = 100
) -> list[dict[str, Any]]:
    return search_transitions(conn, session_id=session_id, limit=limit)


def get_last_finished_map(conn: sqlite3.Connection) -> dict[str, Any]:
    """Latest finished transition's new_updated_at per session (one query).

    Returns {session_id: new_updated_at} for sessions whose latest
    finished-kind transition exists. Used for in-memory dedup in api_sync.
    """
    try:
        rows = conn.execute(
            "SELECT t.session_id AS session_id, t.new_updated_at AS new_updated_at"
            " FROM transitions t"
            " INNER JOIN (SELECT session_id, MAX(id) AS max_id FROM transitions"
            " WHERE kind = 'finished' GROUP BY session_id) m ON m.max_id = t.id"
        ).fetchall()
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for r in rows:
        try:
            out[str(r["session_id"])] = r["new_updated_at"]
        except Exception:
            continue
    return out
