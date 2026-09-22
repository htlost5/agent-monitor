"""P3 verification: transitions DDL + detect pure funcs (epoch) + new endpoints.

Runs against a temp DB (no live OpenCode server):
[1] transitions DDL + insert/list/search round-trip
[2] detect: created / updated / finished / anomaly (epoch comparison)
[3] epoch parity: ISO == epoch-ms == epoch-sec
[4] FINISH_IDLE_SEC == 180 (prod default)
[5] routes: 5 existing unchanged + 2 new (transitions/history)
"""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import detect, store  # noqa: E402


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def main() -> int:
    assert detect.FINISH_IDLE_SEC == 180, f"FINISH_IDLE_SEC={detect.FINISH_IDLE_SEC} != 180"
    print("[0/5] FINISH_IDLE_SEC=180 OK")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "verify_p3.db"
        store.init_db(db)
        conn = store.connect(db)
        try:
            # [1] DDL + insert/list/search
            assert store.list_transitions(conn) == []
            rid = store.insert_transition(conn, "s1", "created", None, "2026-09-21T00:00:00+0000")
            assert isinstance(rid, int) and rid >= 1
            conn.commit()
            rows = store.list_transitions(conn)
            assert len(rows) == 1 and rows[0]["session_id"] == "s1"
            store.insert_transition(conn, "s1", "finished", rows[0]["new_updated_at"],
                                    rows[0]["new_updated_at"], detail="idle>=180s")
            store.insert_transition(conn, "s2", "created", None, "2026-09-21T00:00:00+0000")
            conn.commit()
            assert len(store.list_transitions(conn, limit=10)) == 3
            assert len(store.search_transitions(conn, session_id="s1")) == 2
            assert len(store.search_transitions(conn, kind="created")) == 2
            assert len(store.list_history(conn, "s1")) == 2
            assert store.list_history(conn, "nope") == []
            print("[1/5] transitions DDL+insert/list/search OK")

            # [2] detect 4 kinds (epoch comparison)
            now = time.time()
            fresh = _iso(now - 10)
            idle = _iso(now - 600)
            # created
            ev = detect.diff_snapshots({}, {"a": fresh}, now)
            assert any(e["kind"] == "created" and e["session_id"] == "a" for e in ev), ev
            assert not any(e["kind"] == "finished" for e in ev), ev
            # created + already idle -> created & finished
            ev = detect.diff_snapshots({}, {"b": idle}, now)
            assert any(e["kind"] == "created" for e in ev), ev
            assert any(e["kind"] == "finished" for e in ev), ev
            # updated (epoch advance)
            ev = detect.diff_snapshots({"a": _iso(now - 60)}, {"a": fresh}, now)
            assert any(e["kind"] == "updated" for e in ev), ev
            # finished (same stamp, idle)
            ev = detect.diff_snapshots({"c": idle}, {"c": idle}, now)
            assert any(e["kind"] == "finished" for e in ev), ev
            assert not any(e["kind"] == "updated" for e in ev), ev
            # active (same stamp, recent) -> no event
            ev = detect.diff_snapshots({"d": fresh}, {"d": fresh}, now)
            assert ev == [], ev
            # anomaly: rollback
            ev = detect.diff_snapshots({"e": fresh}, {"e": _iso(now - 3600)}, now)
            assert any(e["kind"] == "anomaly" for e in ev), ev
            # anomaly: unparseable new
            ev = detect.diff_snapshots({"f": fresh}, {"f": "not-a-time"}, now)
            assert any(e["kind"] == "anomaly" for e in ev), ev
            print("[2/5] detect created/updated/finished/anomaly OK")

            # [3] epoch parity
            ep = now - 30
            ms = int(ep * 1000)
            assert detect.to_epoch(_iso(ep)) is not None
            assert abs(detect.to_epoch(_iso(ep)) - ep) < 2.0  # type: ignore[operator]
            assert abs(detect.to_epoch(ms) - ep) < 1.0  # type: ignore[operator]
            assert abs(detect.to_epoch(ep) - ep) < 1e-6  # type: ignore[operator]
            assert detect.to_epoch(None) is None and detect.to_epoch("junk!!!") is None
            print("[3/5] epoch comparison parity OK")
        finally:
            conn.close()

    # [4] routes
    from app.main import app as fastapi_app

    paths = {r.path for r in fastapi_app.routes if hasattr(r, "path")}
    for p in ("/api/health", "/api/sync", "/api/projects", "/api/sessions", "/api/events"):
        assert p in paths, f"existing endpoint missing: {p}"
    for p in ("/api/transitions", "/api/history"):
        assert p in paths, f"new endpoint missing: {p}"
    print("[4/5] routes 5 existing + 2 new OK")

    # [5] real DB initializable with new DDL
    from app.main import resolve_db_path

    store.init_db(resolve_db_path())
    conn = store.connect(resolve_db_path())
    try:
        conn.execute("SELECT id, session_id, kind FROM transitions LIMIT 1").fetchall()
    finally:
        conn.close()
    print("[5/5] real DB transitions table OK")
    print("P3 verify: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
