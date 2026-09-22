"""P4 verification: spec drift warning + offline banners + startup bat.

Runs without live modification (uses TestClient + temp snapshot for pure parts):
[1] spec_snapshot.json exists + contains required endpoints
[2] spec_check pure funcs (extract_paths / diff_paths)
[3] unreachable -> warnings 1件 + ok=false (dict level) + /api/spec-check 200
[4] routes: 7 existing unchanged + GET /api/spec-check new
[5] frontend P4 files (api/useSpecCheck/OfflineBanner/App guards/memo)
[6] root bat + .env.example preview note
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
sys.path.insert(0, str(BACKEND))

from app import spec_check  # noqa: E402


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    # [1] snapshot
    snap_path = spec_check.resolve_snapshot_path()
    assert snap_path.exists(), f"snapshot missing: {snap_path}"
    snap = spec_check.load_snapshot(snap_path)
    assert isinstance(snap, dict) and isinstance(snap.get("paths"), list), "snapshot shape broken"
    assert len(snap["paths"]) > 0, "snapshot paths empty"
    for req in spec_check.REQUIRED_ENDPOINTS:
        assert req in snap["paths"], f"required endpoint not in snapshot: {req}"
    print(f"[1/6] snapshot OK: {snap_path.name} endpoints={len(snap['paths'])}")

    # [2] pure funcs
    assert spec_check.extract_paths({"paths": {"/a": {}, "/b": {}}}) == ["/a", "/b"]
    assert spec_check.extract_paths({}) == []
    assert spec_check.extract_paths(None) == []
    d = spec_check.diff_paths(["/a", "/b"], ["/b", "/c"])
    assert d == {"missing": ["/a"], "extra": ["/c"]}, d
    assert spec_check.diff_paths(["/a"], ["/a"]) == {"missing": [], "extra": []}
    print("[2/6] extract_paths/diff_paths OK")

    # [3] unreachable -> 1 warning + ok=false; endpoint always 200
    bad = spec_check.check_spec(base_url="http://127.0.0.1:9", timeout=1.0)
    assert bad["ok"] is False, bad
    assert bad["reachable"] is False, bad
    assert isinstance(bad["warnings"], list) and len(bad["warnings"]) == 1, bad
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    client = TestClient(fastapi_app)
    r = client.get("/api/spec-check")
    assert r.status_code == 200, f"/api/spec-check status={r.status_code}"
    body = r.json()
    assert isinstance(body.get("ok"), bool), body
    assert isinstance(body.get("warnings"), list), body
    assert isinstance(body.get("reachable"), bool), body
    print("[3/6] unreachable 1-warning + GET /api/spec-check 200 OK")

    # [4] routes
    paths = {r.path for r in fastapi_app.routes if hasattr(r, "path")}
    methods: dict[str, set[str]] = {}
    for r in fastapi_app.routes:
        if hasattr(r, "path") and hasattr(r, "methods"):
            try:
                methods.setdefault(r.path, set()).update(r.methods or set())
            except Exception:
                pass
    for p in (
        "/api/health",
        "/api/sync",
        "/api/projects",
        "/api/sessions",
        "/api/transitions",
        "/api/history",
        "/api/events",
    ):
        assert p in paths, f"existing endpoint missing: {p}"
    assert "/api/spec-check" in paths, "new endpoint missing: /api/spec-check"
    assert "GET" in methods.get("/api/spec-check", set()), "spec-check must be GET"
    print("[4/6] routes 7 existing + spec-check(GET) OK")

    # [5] frontend files
    fe = REPO / "frontend" / "src"
    api_ts = _read(fe / "api.ts")
    assert "SpecCheckResponse" in api_ts, "api.ts missing SpecCheckResponse"
    assert "fetchSpecCheck" in api_ts, "api.ts missing fetchSpecCheck"
    assert "/api/spec-check" in api_ts, "api.ts missing /api/spec-check path"

    hook_p = fe / "hooks" / "useSpecCheck.ts"
    assert hook_p.exists(), "hooks/useSpecCheck.ts missing"
    hook = _read(hook_p)
    assert "fetchSpecCheck" in hook, "useSpecCheck must use fetchSpecCheck"
    assert "inflight" in hook.lower() or "in-flight" in hook.lower() or "inFlight" in hook, \
        "useSpecCheck missing in-flight guard"

    banner_p = fe / "components" / "OfflineBanner.tsx"
    assert banner_p.exists(), "components/OfflineBanner.tsx missing"
    banner = _read(banner_p)
    assert "backendReachable" in banner and "opencodeReachable" in banner, \
        "OfflineBanner props must cover backend/opencode"
    assert "Alert" in banner, "OfflineBanner must render MUI Alert"

    app_tsx = _read(fe / "App.tsx")
    assert "useSpecCheck" in app_tsx, "App.tsx must use useSpecCheck"
    assert "OfflineBanner" in app_tsx, "App.tsx must render OfflineBanner"

    sessions_ts = _read(fe / "useSessions.ts")
    assert "useMemo" in sessions_ts, "useSessions must memoize projectMap (useMemo)"
    assert "inflight" in sessions_ts.lower() or "inflightref" in sessions_ts.lower().replace("_", ""), \
        "useSessions missing in-flight guard"

    notify_ts = _read(fe / "hooks" / "useTransitionNotify.ts")
    assert "useMemo" in notify_ts or "memo" in notify_ts.lower(), \
        "useTransitionNotify must memoize derived maps"
    assert "inflight" in notify_ts.lower() or "in_flight" in notify_ts.lower(), \
        "useTransitionNotify missing in-flight guard"

    grid_tsx = _read(fe / "components" / "SessionGrid.tsx")
    assert "memo" in grid_tsx, "SessionGrid must be memoized (memo)"
    print("[5/6] frontend api/hook/banner/App guards+memo OK")

    # [6] bat + .env.example note
    bat = REPO / "start-oc-monitor.bat"
    assert bat.exists(), "root start-oc-monitor.bat missing"
    bat_s = _read(bat)
    assert "4100" in bat_s and "5173" in bat_s, "bat must start 4100 + 5173"
    assert ".venv" in bat_s, "bat must use backend/.venv"
    assert "/k" in bat_s, "bat must keep windows (/k)"
    env_ex = _read(REPO / "frontend" / ".env.example")
    assert "preview" in env_ex.lower(), ".env.example must contain vite preview note"
    print("[6/6] bat + .env.example preview note OK")

    print("P4 verify: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
