"""P1 verification: row-count match + idempotent upsert.

Runs against a temp DB (no live OpenCode server, no message fetch):
1. Insert N projects + M sessions -> counts must match.
2. Re-upsert the SAME payloads -> counts must be unchanged (idempotent).
3. sync_state set/get round-trip.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "verify_p1.db"
        store.init_db(db)
        conn = store.connect(db)
        try:
            projects = [
                {"id": f"p{i}", "name": f"proj-{i}", "path": f"/tmp/proj-{i}"}
                for i in range(5)
            ]
            sessions = [
                {
                    "id": f"s{i}",
                    "project_id": f"p{i % 5}",
                    "title": f"session-{i}",
                    "updated_at": "2026-09-21T00:00:00+0000",
                }
                for i in range(12)
            ]

            for p in projects:
                store.upsert_project(conn, p["id"], p["name"], p["path"], raw=p)
            for s in sessions:
                store.upsert_session(
                    conn, s["id"], s["project_id"], s["title"], s["updated_at"], raw=s
                )
            conn.commit()

            n_p, n_s = store.count_projects(conn), store.count_sessions(conn)
            assert n_p == len(projects), f"projects count mismatch: {n_p} != {len(projects)}"
            assert n_s == len(sessions), f"sessions count mismatch: {n_s} != {len(sessions)}"
            print(f"[1/3] count match OK: projects={n_p} sessions={n_s}")

            # Idempotent re-upsert of identical payloads
            for p in projects:
                store.upsert_project(conn, p["id"], p["name"], p["path"], raw=p)
            for s in sessions:
                store.upsert_session(
                    conn, s["id"], s["project_id"], s["title"], s["updated_at"], raw=s
                )
            # Update one row's non-key field: count must NOT grow
            store.upsert_project(conn, "p0", "proj-0-renamed", "/tmp/proj-0", raw=projects[0])
            conn.commit()

            n_p2, n_s2 = store.count_projects(conn), store.count_sessions(conn)
            assert (n_p2, n_s2) == (n_p, n_s), (
                f"idempotency broken: before=({n_p},{n_s}) after=({n_p2},{n_s2})"
            )
            renamed = [r for r in store.list_projects(conn) if r["id"] == "p0"][0]
            assert renamed["name"] == "proj-0-renamed", "upsert update path broken"
            print(f"[2/3] idempotent upsert OK: projects={n_p2} sessions={n_s2}")

            store.set_sync_state(conn, "last_sync", "2026-09-21T00:00:00+0000")
            conn.commit()
            assert store.get_sync_state(conn, "last_sync") == "2026-09-21T00:00:00+0000"
            assert store.get_sync_state(conn, "no_such_key") is None
            print("[3/3] sync_state round-trip OK")
        finally:
            conn.close()

    # Real DB file must be initializable too (creates backend/data/oc_monitor.db)
    from app.main import resolve_db_path

    store.init_db(resolve_db_path())
    assert resolve_db_path().exists(), "real DB file was not created"
    print(f"[extra] real DB ready: {resolve_db_path()}")
    print("P1 verify: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
