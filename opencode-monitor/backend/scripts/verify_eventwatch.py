"""P5 verification: event-driven sync (no live servers needed).

[1] parse_event_type: real /global/event wire shapes
[2] is_sync_trigger: heartbeat/connected/sync ignored, session.* fire
[3] config: EVENTWATCH_ENABLED/DEBOUNCE/SAFETY env parsing
[4] routes: POST /api/sync kept + GET /api/eventwatch new (+7 existing intact)
[5] /api/eventwatch 200 shape (watcher disabled) + frontend P5 markers
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
sys.path.insert(0, str(BACKEND))

from app import eventwatch  # noqa: E402


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    # [1] wire shapes (captured live from opencode 1.18.31 /global/event)
    assert eventwatch.parse_event_type(
        'data: {"payload":{"id":"evt_x","type":"server.connected","properties":{}}}'
    ) == "server.connected"
    assert eventwatch.parse_event_type(
        'data: {"directory":"global","project":"global",'
        '"payload":{"type":"session.created","properties":{"sessionID":"ses_1"},'
        '"id":"evt_y"}}'
    ) == "session.created"
    assert eventwatch.parse_event_type(
        'data: {"directory":"d","project":"p",'
        '"payload":{"type":"sync","syncEvent":{"type":"session.created.1"}}}'
    ) == "sync"
    assert eventwatch.parse_event_type(": heartbeat") is None
    assert eventwatch.parse_event_type("") is None
    assert eventwatch.parse_event_type("data: not-json") is None
    assert eventwatch.parse_event_type("data: [1,2]") is None
    assert eventwatch.parse_event_type("data: {}") is None
    print("[1/5] parse_event_type OK")

    # [2] trigger decision
    for t in ("session.created", "session.updated", "session.deleted",
              "message.updated", "session.error", "reconnected",
              "something.future"):
        assert eventwatch.is_sync_trigger(t) is True, t
    for t in ("server.connected", "server.heartbeat", "sync", None, ""):
        assert eventwatch.is_sync_trigger(t) is False, t
    print("[2/5] is_sync_trigger OK")

    # [3] config parsing (reload with env overrides)
    import app.config as config

    old = dict(os.environ)
    try:
        os.environ["EVENTWATCH_ENABLED"] = "0"
        os.environ["EVENT_DEBOUNCE_SEC"] = "0.5"
        os.environ["EVENT_SAFETY_SEC"] = "0"
        importlib.reload(config)
        assert config.EVENTWATCH_ENABLED == 0, config.EVENTWATCH_ENABLED
        assert config.EVENT_DEBOUNCE_SEC == 0.5, config.EVENT_DEBOUNCE_SEC
        assert config.EVENT_SAFETY_SEC == 0.0, config.EVENT_SAFETY_SEC
        os.environ["EVENTWATCH_ENABLED"] = "no"
        os.environ["EVENT_DEBOUNCE_SEC"] = "bogus"
        os.environ["EVENT_SAFETY_SEC"] = "-5"
        importlib.reload(config)
        assert config.EVENTWATCH_ENABLED == 0
        assert config.EVENT_DEBOUNCE_SEC == 2.0
        assert config.EVENT_SAFETY_SEC == 0.0
    finally:
        os.environ.clear()
        os.environ.update(old)
        importlib.reload(config)
    assert config.EVENTWATCH_ENABLED == 1
    assert config.EVENT_DEBOUNCE_SEC == 2.0
    assert config.EVENT_SAFETY_SEC == 60.0
    print("[3/5] config parsing OK")

    # [4] routes intact + new
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    methods: dict[str, set[str]] = {}
    for r in fastapi_app.routes:
        if hasattr(r, "path") and hasattr(r, "methods"):
            try:
                methods.setdefault(r.path, set()).update(r.methods or set())
            except Exception:
                pass
    for p, m in (
        ("/api/health", "GET"), ("/api/sync", "POST"),
        ("/api/projects", "GET"), ("/api/sessions", "GET"),
        ("/api/transitions", "GET"), ("/api/history", "GET"),
        ("/api/spec-check", "GET"), ("/api/events", "GET"),
        ("/api/eventwatch", "GET"),
    ):
        assert m in methods.get(p, set()), f"{m} {p} missing"
    print("[4/5] routes 8 existing + eventwatch(GET) OK")

    # [5] /api/eventwatch shape (watcher disabled by default TestClient lifespan?
    # TestClient runs lifespan -> watcher would try to connect; unreachable here
    # means reconnect loop in background, harmless. Shape assert only.)
    client = TestClient(fastapi_app)
    r = client.get("/api/eventwatch")
    assert r.status_code == 200, r.status_code
    body = r.json()
    for k in ("enabled", "connected", "triggers", "syncs", "reconnects",
              "debounce_sec", "safety_sec", "base_url"):
        assert k in body, f"key missing: {k}"
    fe_use = _read(REPO / "frontend" / "src" / "useSessions.ts")
    assert "}, 5000)" not in fe_use, "5s interval remains in useSessions.ts"
    assert "60000" in fe_use, "60s safety net missing in useSessions.ts"
    assert "visibilitychange" in fe_use, "visibility refresh missing"
    fe_tn = _read(REPO / "frontend" / "src" / "hooks" / "useTransitionNotify.ts")
    assert "pollMs = 60000" in fe_tn, "transition poll not 60s"
    fe_app = _read(REPO / "frontend" / "src" / "App.tsx")
    assert '"standby"' in fe_app and '"polling"' not in fe_app
    print("[5/5] /api/eventwatch 200 + frontend P5 markers OK")
    print("P5 verify_eventwatch: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
