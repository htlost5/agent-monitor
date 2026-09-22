"""P5 live E2E: pseudo tasks -> opencode events -> backend sync -> transitions.

Requires (started separately):
  opencode serve --port 4096
  backend uvicorn with EVENTWATCH_ENABLED=1, EVENT_DEBOUNCE_SEC~1,
  EVENT_SAFETY_SEC=0 (isolate the event path), FINISH_IDLE_SEC~10,
  DB_PATH=<throwaway test db>.

This script NEVER calls POST /api/sync: every observed transition must
come from the event-driven path (or the test fails).

Steps:
  [1] create session -> kind=created transition appears
  [2] PATCH title    -> kind=updated appears
  [3] idle > FINISH_IDLE, then create session-2 -> kind=finished for session-1
      (cross-session event sync detects completion) + created for session-2
  [4] delete both    -> backend stays healthy, syncs keep advancing
  [5] backend /api/events SSE delivered sync notifications carrying our transitions
"""

from __future__ import annotations

import os
import sys
import threading
import time

import httpx

BACKEND = os.environ.get("E2E_BACKEND", "http://127.0.0.1:4100")
OPENCODE = os.environ.get("E2E_OPENCODE", "http://127.0.0.1:4096")
WORKDIR = os.environ.get(
    "E2E_WORKDIR",
    "C:/Users/MyPC/AppData/Local/hermes/cache/scratch/e2e-probe",
)
FINISH_IDLE = float(os.environ.get("E2E_FINISH_IDLE", "10"))

oc = httpx.Client(base_url=OPENCODE, timeout=10.0)
be = httpx.Client(base_url=BACKEND, timeout=10.0)

failures: list[str] = []
sse_sync_payloads: list[dict] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond:
        failures.append(name)


def wait_eventwatch_connected(timeout: float = 30.0) -> dict:
    t0 = time.time()
    last: dict = {}
    while time.time() - t0 < timeout:
        try:
            last = be.get("/api/eventwatch").json()
            if last.get("enabled") and last.get("connected"):
                return last
        except Exception:
            pass
        time.sleep(1.0)
    return last


def sse_listener(stop: threading.Event, deadline: float) -> None:
    import json as _json

    try:
        with httpx.stream(
            "GET", f"{BACKEND}/api/events", timeout=httpx.Timeout(5, read=60)
        ) as r:
            for line in r.iter_lines():
                if stop.is_set() or time.time() > deadline:
                    break
                s = (line or "").strip()
                if s.startswith("data:"):
                    try:
                        obj = _json.loads(s[5:])
                    except Exception:
                        continue
                    if isinstance(obj, dict) and obj.get("type") == "sync":
                        sse_sync_payloads.append(obj)
    except Exception as e:
        print("sse listener ended:", type(e).__name__, e)


def transitions_for(sid: str) -> list[dict]:
    try:
        r = be.get("/api/transitions", params={"session_id": sid, "limit": 100})
        items = r.json().get("transitions", [])
        return [t for t in items if isinstance(t, dict)]
    except Exception:
        return []


def wait_kind(sid: str, kind: str, timeout: float, since_id: int = 0) -> dict | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        for t in transitions_for(sid):
            if t.get("kind") == kind and int(t.get("id", 0)) > since_id:
                return t
        time.sleep(1.0)
    return None


def max_transition_id() -> int:
    try:
        items = be.get("/api/transitions", params={"limit": 1}).json().get("transitions", [])
        return int(items[0].get("id", 0)) if items else 0
    except Exception:
        return 0


def main() -> int:
    os.makedirs(WORKDIR, exist_ok=True)
    created: list[str] = []
    try:
        st = wait_eventwatch_connected()
        check("watcher connected", bool(st.get("enabled") and st.get("connected")), str(st))
        if failures:
            return 1
        base_id = max_transition_id()

        stop = threading.Event()
        deadline = time.time() + 180
        th = threading.Thread(target=sse_listener, args=(stop, deadline), daemon=True)
        th.start()

        # [1] create session-1
        s1 = oc.post(
            "/session", params={"directory": WORKDIR}, json={"title": "e2e-probe-1"}
        ).json()
        sid1 = s1["id"]
        created.append(sid1)
        t = wait_kind(sid1, "created", 25, base_id)
        check("created detected via events (no manual sync)", t is not None, f"sid={sid1[:12]}")

        # [2] title update: PATCH does NOT bump opencode time.updated
        # (verified live), so no `updated` transition is CORRECT. Assert instead
        # that the session.updated event triggered a sync which refreshed data.
        syncs_before2 = be.get("/api/eventwatch").json().get("syncs", 0)
        time.sleep(2)
        oc.patch(f"/session/{sid1}", json={"title": "e2e-probe-1-renamed"})
        t0 = time.time()
        cur = syncs_before2
        while time.time() - t0 < 20:
            try:
                cur = be.get("/api/eventwatch").json().get("syncs", 0)
                if cur > syncs_before2:
                    break
            except Exception:
                pass
            time.sleep(1.0)
        check("sync triggered by session.updated event", cur > syncs_before2,
              f"syncs {syncs_before2}->{cur}")
        title_now = None
        try:
            items = be.get("/api/sessions", params={"limit": 200}).json().get("sessions", [])
            title_now = next((s.get("title") for s in items if s.get("id") == sid1), None)
        except Exception:
            pass
        check("event sync refreshed session data", title_now == "e2e-probe-1-renamed",
              f"title={title_now!r}")

        # [3] idle past FINISH_IDLE, then session-2 create triggers cross sync
        print(f"waiting idle {FINISH_IDLE + 3:.0f}s ...")
        time.sleep(FINISH_IDLE + 3)
        s2 = oc.post(
            "/session", params={"directory": WORKDIR}, json={"title": "e2e-probe-2"}
        ).json()
        sid2 = s2["id"]
        created.append(sid2)
        tf = wait_kind(sid1, "finished", 25, base_id)
        check("idle finished detected via cross-session event sync",
              tf is not None, f"sid={sid1[:12]} detail={(tf or {}).get('detail')}")
        tc2 = wait_kind(sid2, "created", 25, base_id)
        check("session-2 created detected", tc2 is not None, f"sid={sid2[:12]}")

        # [4] delete both; backend must stay healthy and keep syncing
        syncs_before = be.get("/api/eventwatch").json().get("syncs", 0)
        for sid in list(created):
            try:
                oc.delete(f"/session/{sid}")
            except Exception:
                pass
        created.clear()
        t0 = time.time()
        advanced = False
        while time.time() - t0 < 25:
            try:
                cur = be.get("/api/eventwatch").json().get("syncs", 0)
                if cur > syncs_before:
                    advanced = True
                    break
            except Exception:
                pass
            time.sleep(1.0)
        h = be.get("/api/health").json()
        check("sync advanced on delete events", advanced, f"syncs {syncs_before}->{cur}")
        check("backend healthy after deletes", h.get("status") == "ok", str(h.get("db")))

        # [5] SSE push path (what the frontend listens to)
        stop.set()
        th.join(timeout=10)
        ours = [
            p for p in sse_sync_payloads
            if any(
                isinstance(t, dict) and t.get("session_id") in (sid1, sid2)
                for t in (p.get("transitions") or [])
            )
        ]
        check("SSE sync notifications carried our transitions",
              len(ours) >= 1, f"sync_notifs={len(sse_sync_payloads)} ours={len(ours)}")
    finally:
        for sid in created:
            try:
                oc.delete(f"/session/{sid}")
            except Exception:
                pass

    print("E2E", "ALL OK" if not failures else f"FAILURES={failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
