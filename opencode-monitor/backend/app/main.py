"""FastAPI backend: health / sync / sessions / projects / SSE events."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import config
from . import detect
from . import eventwatch
from . import spec_check
from . import store
from .opencode_client import OpenCodeClient

subscribers: set[asyncio.Queue] = set()

# --- P5 event-driven sync state -------------------------------------------
# Single-worker premise: exactly one /global/event subscription per backend.
_event_status: dict[str, Any] = {
    "enabled": False,
    "connected": False,
    "connected_at": None,
    "last_event_type": None,
    "last_event_at": None,
    "triggers": 0,
    "last_trigger": None,
    "last_trigger_at": None,
    "syncs": 0,
    "last_sync_at": None,
    "last_error": None,
    "reconnects": 0,
}
_sync_debounce_handle: Optional[Any] = None
_sync_inflight = False
# Lifespan-captured loop: lets run_sync broadcast SSE from any thread
# (route threadpool / asyncio.to_thread have no running loop).
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def broadcast_sync_result(
    n_projects: int, n_sessions: int, recorded: list[dict[str, Any]]
) -> None:
    """Schedule a "sync" SSE message on the app loop (thread-safe)."""
    try:
        msg = json.dumps(
            {
                "type": "sync",
                "projects": n_projects,
                "sessions": n_sessions,
                "transitions": recorded,
            }
        )
    except Exception:
        return
    loop = _main_loop
    if loop is None:
        return
    try:
        if not loop.is_running():
            return
        fut = asyncio.run_coroutine_threadsafe(_broadcast(msg), loop)
        fut.add_done_callback(lambda f: f.exception())
    except Exception:
        pass


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def request_sync(source: str) -> None:
    """Request a debounced event-driven sync (async contexts only).

    Trailing edge: rapid events (streaming deltas) coalesce into one sync
    EVENT_DEBOUNCE_SEC after the last trigger. A sync already running
    postpones the next run instead of overlapping it.
    """
    global _sync_debounce_handle
    _event_status["last_trigger"] = source
    _event_status["last_trigger_at"] = _utcnow_iso()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _sync_debounce_handle is not None:
        try:
            _sync_debounce_handle.cancel()
        except Exception:
            pass
    try:
        delay = float(config.EVENT_DEBOUNCE_SEC)
    except Exception:
        delay = 2.0
    if not (delay > 0):
        delay = 2.0
    _sync_debounce_handle = loop.call_later(
        delay, lambda: loop.create_task(_do_debounced_sync())
    )


async def _do_debounced_sync() -> None:
    global _sync_debounce_handle, _sync_inflight
    _sync_debounce_handle = None
    if _sync_inflight:
        request_sync("coalesced")
        return
    _sync_inflight = True
    try:
        await asyncio.to_thread(run_sync)
        _event_status["syncs"] = int(_event_status.get("syncs", 0)) + 1
        _event_status["last_sync_at"] = _utcnow_iso()
        _event_status["last_error"] = None
    except HTTPException as e:
        _event_status["last_error"] = f"HTTPException: {e.status_code}"
    except Exception as e:
        _event_status["last_error"] = f"{type(e).__name__}: {e}"
    finally:
        _sync_inflight = False


def _on_opencode_event(event_type: str) -> None:
    request_sync(f"event:{event_type}")


async def _safety_loop() -> None:
    """Long-interval safety net (missed events / schema drift / downtime gaps)."""
    try:
        interval = float(config.EVENT_SAFETY_SEC)
    except Exception:
        interval = 60.0
    while True:
        await asyncio.sleep(interval)
        request_sync("safety")


def resolve_db_path() -> Path:
    p = Path(config.DB_PATH)
    if p.is_absolute():
        return p
    # DB_PATH default "backend/data/oc_monitor.db" is repo-root relative.
    # Resolve against repo root (= parents[2] of this file: .../oc-monitor)
    # so `uvicorn app.main:app` from backend/ and from repo root share one DB.
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / p


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    store.init_db(resolve_db_path())
    tasks: list[asyncio.Task] = []
    try:
        enabled = int(config.EVENTWATCH_ENABLED) != 0
    except Exception:
        enabled = True
    if enabled:
        _event_status["enabled"] = True
        tasks.append(
            asyncio.create_task(
                eventwatch.watch_forever(
                    config.OPENCODE_BASE_URL, _on_opencode_event, _event_status
                )
            )
        )
        try:
            safety_sec = float(config.EVENT_SAFETY_SEC)
        except Exception:
            safety_sec = 60.0
        if safety_sec > 0:
            tasks.append(asyncio.create_task(_safety_loop()))
    yield
    for t in tasks:
        try:
            t.cancel()
        except Exception:
            pass


app = FastAPI(title="oc-monitor backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("sessions", "projects", "data", "items"):
            v = payload.get(key)
            if isinstance(v, list):
                return [p for p in v if isinstance(p, dict)]
    return []


def _pick(d: dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def _pick_nested(d: dict[str, Any], *paths: Any) -> Optional[Any]:
    """Pick first non-None nested value. Each path is a tuple/list of keys or a dot-string."""
    for path in paths:
        if isinstance(path, str):
            keys = path.split(".")
        else:
            keys = list(path)
        cur: Any = d
        ok = True
        for k in keys:
            if isinstance(cur, dict) and cur.get(k) is not None:
                cur = cur.get(k)
            else:
                ok = False
                break
        if ok:
            return cur
    return None


def _epoch_ms_to_iso(v: Any) -> Optional[str]:
    """Map epoch-ms (int/float) or ISO string to ISO string. None stays None."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        from datetime import datetime, timezone

        ts = float(v)
        # Heuristic: ms (>1e12) vs seconds (>1e9). OpenCode uses epoch-ms.
        if ts > 1e12:
            ts = ts / 1000.0
        elif ts > 1e11:
            # Unlikely range; treat as ms as well.
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _as_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return None


def _session_updated_at(s: dict[str, Any]) -> Optional[str]:
    flat = _pick(s, "updatedAt", "updated_at", "updated", "timeUpdated")
    if isinstance(flat, str):
        return flat
    if isinstance(flat, (int, float)) and not isinstance(flat, bool):
        iso = _epoch_ms_to_iso(flat)
        if iso is not None:
            return iso
    nested = _pick_nested(s, ("time", "updated"), ("time", "created"), "time.updated")
    return _epoch_ms_to_iso(nested) if nested is not None else None


async def _broadcast(message: str) -> None:
    for q in list(subscribers):
        await q.put(message)


@app.get("/api/health")
def api_health() -> dict[str, Any]:
    db_ok = False
    try:
        conn = store.connect(resolve_db_path())
        try:
            # Read-only check: SELECT only, no writes here.
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        finally:
            conn.close()
    except Exception:
        db_ok = False
    opencode: dict[str, Any] = {"reachable": False}
    try:
        with OpenCodeClient(config.OPENCODE_BASE_URL, timeout=2.0) as client:
            opencode["reachable"] = True
            opencode["health"] = client.get_health()
    except Exception as e:  # best-effort: API itself stays 200
        opencode["error"] = f"{type(e).__name__}: {e}"
    return {"status": "ok", "db": "ok" if db_ok else "ng", "opencode": opencode}


def run_sync() -> dict[str, Any]:
    """opencode -> DB sync core (shared by POST /api/sync and event watcher).

    Raises HTTPException(503) when opencode is unreachable (route contract
    unchanged). Broadcasts a "sync" SSE message on completion, same as before.
    Blocking (sync httpx client): background tasks must run it via to_thread.
    """
    import time as _time
    import warnings as _warnings

    t0 = _time.perf_counter()
    # Single httpx.Client reused for all opencode calls in this sync
    # (session list + TASK-3 marker message fetch share one client).
    http: httpx.Client | None = None
    try:
        http = httpx.Client(base_url=config.OPENCODE_BASE_URL, timeout=config.SYNC_TIMEOUT)
        client = OpenCodeClient(
            config.OPENCODE_BASE_URL, timeout=config.SYNC_TIMEOUT, client=http
        )
        try:
            raw_projects = client.list_projects()
            # Primary: webui /api/session (max_pages=SYNC_MAX_PAGES, default 8).
            raw_sessions = client.list_sessions(max_pages=config.SYNC_MAX_PAGES)
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=503,
                detail={"opencode_reachable": False, "error": f"opencode unreachable: {e}"},
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail={"opencode_reachable": False, "error": f"opencode unreachable: {e}"},
            )
    except HTTPException:
        if http is not None:
            try:
                http.close()
            except Exception:
                pass
        raise
    warnings: list[str] = []
    if raw_projects is None:
        msg = "opencode projects empty response (treated as warning)"
        _warnings.warn(msg)
        warnings.append(msg)
    if raw_sessions is None:
        msg = "opencode sessions empty response (treated as warning)"
        _warnings.warn(msg)
        warnings.append(msg)
    projects = _as_list(raw_projects)
    sessions = _as_list(raw_sessions)
    if not projects and raw_projects is not None:
        warnings.append("projects empty (warning)")
    if not sessions and raw_sessions is not None:
        warnings.append("sessions empty (warning)")

    db_path = resolve_db_path()
    store.init_db(db_path)
    conn = store.connect(db_path)
    try:
        # Diff-only upsert: old snapshots for sessions + projects.
        old_map: dict[str, Any] = {}
        old_sess_fields: dict[str, tuple[Any, Any, Any]] = {}
        try:
            for r in conn.execute(
                "SELECT id, project_id, title, updated_at FROM sessions"
            ).fetchall():
                sid = str(r["id"])
                old_map[sid] = r["updated_at"]
                old_sess_fields[sid] = (r["project_id"], r["title"], r["updated_at"])
        except Exception:
            old_map = {}
            old_sess_fields = {}
        old_proj_fields: dict[str, tuple[Any, Any]] = {}
        try:
            for r in conn.execute("SELECT id, name, path FROM projects").fetchall():
                old_proj_fields[str(r["id"])] = (r["name"], r["path"])
        except Exception:
            old_proj_fields = {}
        new_map: dict[str, Any] = {}
        new_project_ids: set[str] = set()
        upserted_projects = 0
        upserted_sessions = 0
        for p in projects:
            pid_raw = _pick(p, "id", "projectID", "projectId")
            if pid_raw is None:
                continue
            pid = str(pid_raw)
            new_project_ids.add(pid)
            # No dummy: missing name stays None (do not invent from id/path).
            name = _as_str(_pick(p, "name", "title"))
            path = _as_str(_pick(p, "path", "directory", "worktree"))
            old = old_proj_fields.get(pid)
            if old is not None and old[0] == name and old[1] == path:
                continue  # unchanged: skip upsert (no json.dumps, no write)
            store.upsert_project(
                conn,
                project_id=pid,
                name=name,
                path=path,
                raw=p,
            )
            upserted_projects += 1
        for s in sessions:
            sid_raw = _pick(s, "id", "sessionId", "sessionID")
            if sid_raw is None:
                continue
            sid = str(sid_raw)
            uat = _session_updated_at(s)
            new_map[sid] = uat
            proj = _as_str(_pick(s, "projectID", "projectId", "project_id"))
            title = _as_str(_pick(s, "title", "name"))
            old = old_sess_fields.get(sid)
            if (
                old is not None
                and old[0] == proj
                and old[1] == title
                and old[2] == uat
            ):
                continue  # unchanged: skip upsert (synced_at untouched)
            store.upsert_session(
                conn,
                session_id=sid,
                project_id=proj,
                title=title,
                updated_at=uat,
                raw=s,
            )
            upserted_sessions += 1
        import time as _time

        store.set_sync_state(conn, "last_sync", _time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        store.set_sync_state(conn, "last_counts", json.dumps({"projects": len(projects), "sessions": len(sessions)}))
        conn.commit()
        # Diff (epoch comparison) -> record transitions (finished deduped) -> SSE.
        import time as _time2

        now_epoch = _time2.time()
        try:
            events = detect.diff_snapshots(old_map, new_map, now_epoch)
        except Exception:
            events = []
        # Batch: latest finished new_updated_at per session (one query).
        try:
            last_finished_map = store.get_last_finished_map(conn)
        except Exception:
            last_finished_map = {}
        recorded: list[dict[str, Any]] = []
        for ev in events:
            try:
                if ev.get("kind") == "finished":
                    prev_ts = last_finished_map.get(str(ev.get("session_id", "")))
                    if prev_ts is not None:
                        # Epoch comparison (1s tolerance); fallback to string match.
                        prev_ep = detect.to_epoch(prev_ts)
                        cur_ep = detect.to_epoch(ev.get("new_updated_at"))
                        if prev_ep is not None and cur_ep is not None:
                            if abs(prev_ep - cur_ep) <= 1.0:
                                continue  # already reported idle: suppress repeat
                        elif prev_ts == ev.get("new_updated_at"):
                            continue
                rid = store.insert_transition(
                    conn,
                    session_id=str(ev.get("session_id", "")),
                    kind=str(ev.get("kind", "")),
                    old_updated_at=ev.get("old_updated_at"),
                    new_updated_at=ev.get("new_updated_at"),
                    detail=ev.get("detail"),
                )
                recorded.append({"id": rid, **ev})
            except Exception:
                continue
        # TASK-3 marker: active-only immediate finished (same client, sequential).
        # Existing diff above is unchanged; marker hits synthesize extra finished.
        marker_checked = 0
        marker_hit = 0
        marker_skipped = 0
        try:
            _me = getattr(config, "MARKER_ENABLED", 1)
            _parser = getattr(config, "_parse_marker_enabled", None)
            if isinstance(_me, str) and callable(_parser):
                # Canonical disable notation is MARKER_ENABLED=0;
                # false/no/off are accepted as aliases via the parser.
                marker_enabled = _parser(_me) != 0
            else:
                marker_enabled = int(_me) != 0
        except Exception:
            marker_enabled = True
        if marker_enabled:
            try:
                _idle_sec = float(detect.FINISH_IDLE_SEC)
            except Exception:
                _idle_sec = 180.0
            try:
                _max_sess = int(config.MARKER_MAX_SESSIONS)
            except Exception:
                _max_sess = 20
            try:
                _msg_limit = int(config.MARKER_MSG_LIMIT)
            except Exception:
                _msg_limit = 10
            try:
                _marker_str = str(config.MARKER_STRING)
            except Exception:
                _marker_str = "__HERMES_TASK_DONE__"
            try:
                _marker_timeout = float(getattr(config, "MARKER_TIMEOUT", 3.0))
            except Exception:
                _marker_timeout = 3.0
            if not (_marker_timeout > 0):
                _marker_timeout = 3.0
            scored: list[tuple[float, str]] = []
            for _sid, _uat in new_map.items():
                try:
                    _ep = detect.to_epoch(_uat)
                except Exception:
                    _ep = None
                try:
                    if _ep is not None and detect.is_active(_ep, now_epoch, _idle_sec):
                        scored.append((float(_ep), str(_sid)))
                except Exception:
                    continue
            scored.sort(key=lambda x: x[0], reverse=True)
            candidates = [sid for _, sid in scored[:_max_sess]]
            marker_skipped = len(scored) - len(candidates)
            # Whole-phase time budget (MARKER_TIMEOUT) + early cutoff, with
            # per-request timeout = MARKER_TIMEOUT (clamped to remaining).
            try:
                _marker_deadline = _time.perf_counter() + float(_marker_timeout)
            except Exception:
                _marker_deadline = None
            for _idx, _sid in enumerate(candidates):
                if _marker_deadline is not None:
                    try:
                        _remaining = _marker_deadline - _time.perf_counter()
                    except Exception:
                        _remaining = float(_marker_timeout)
                    if _remaining <= 0:
                        marker_skipped += len(candidates) - _idx
                        break
                    _req_timeout = (
                        float(_marker_timeout)
                        if _remaining >= float(_marker_timeout)
                        else max(0.05, float(_remaining))
                    )
                else:
                    _req_timeout = float(_marker_timeout)
                try:
                    _msgs = client.get_session_messages(
                        _sid, limit=_msg_limit, timeout=_req_timeout
                    )
                except Exception as e:
                    _m = f"marker fetch failed for {_sid[:12]} (treated as warning): {type(e).__name__}"
                    try:
                        _warnings.warn(_m)
                    except Exception:
                        pass
                    warnings.append(_m)
                    marker_skipped += 1
                    continue
                marker_checked += 1
                try:
                    _hit = detect.has_marker(_msgs, _marker_str)
                except Exception:
                    _hit = False
                if not _hit:
                    continue
                _cur_uat = new_map.get(_sid)
                try:
                    _cur_ep = detect.to_epoch(_cur_uat)
                except Exception:
                    _cur_ep = None
                _dup = False
                _prev_ts = last_finished_map.get(_sid)
                if _prev_ts is not None:
                    try:
                        _prev_ep = detect.to_epoch(_prev_ts)
                        if _prev_ep is not None and _cur_ep is not None:
                            if abs(_prev_ep - _cur_ep) <= 1.0:
                                _dup = True
                        elif _prev_ts == _cur_uat:
                            _dup = True
                    except Exception:
                        pass
                if not _dup:
                    for _r in recorded:
                        try:
                            if str(_r.get("session_id")) == _sid and _r.get("kind") == "finished":
                                _r_ep = detect.to_epoch(_r.get("new_updated_at"))
                                if _r_ep is not None and _cur_ep is not None:
                                    if abs(_r_ep - _cur_ep) <= 1.0:
                                        _dup = True
                                        break
                                elif _r.get("new_updated_at") == _cur_uat:
                                    _dup = True
                                    break
                        except Exception:
                            continue
                if _dup:
                    continue
                try:
                    _rid = store.insert_transition(
                        conn,
                        session_id=_sid,
                        kind="finished",
                        old_updated_at=old_map.get(_sid),
                        new_updated_at=_cur_uat,
                        detail=f"marker:{_marker_str} (即時確定)",
                    )
                    recorded.append(
                        {
                            "id": _rid,
                            "session_id": _sid,
                            "kind": "finished",
                            "old_updated_at": old_map.get(_sid),
                            "new_updated_at": _cur_uat,
                            "detail": f"marker:{_marker_str} (即時確定)",
                        }
                    )
                    marker_hit += 1
                except Exception:
                    continue
        else:
            try:
                _idle_sec2 = float(detect.FINISH_IDLE_SEC)
            except Exception:
                _idle_sec2 = 180.0
            _n_active = 0
            for _sid, _uat in new_map.items():
                try:
                    if detect.is_active(detect.to_epoch(_uat), now_epoch, _idle_sec2):
                        _n_active += 1
                except Exception:
                    continue
            marker_skipped = _n_active
        if recorded:
            conn.commit()
        # len() alternative (no COUNT x2 queries): union of old + new ids.
        n_projects = len(set(old_proj_fields) | new_project_ids)
        n_sessions = len(set(old_map) | set(new_map))
    finally:
        conn.close()

    # Notify SSE subscribers (thread-safe via lifespan-captured loop).
    broadcast_sync_result(n_projects, n_sessions, recorded)
    result: dict[str, Any] = {"projects": n_projects, "sessions": n_sessions, "synced": True}
    if recorded:
        result["transitions"] = recorded
    if warnings:
        result["warnings"] = warnings
    # Measurement fields (existing fields unchanged).
    import time as _time3

    result["duration_ms"] = int((_time3.perf_counter() - t0) * 1000)
    result["fetched"] = {"projects": len(projects), "sessions": len(sessions)}
    result["upserted"] = {"projects": upserted_projects, "sessions": upserted_sessions}
    result["marker"] = {"checked": marker_checked, "hit": marker_hit, "skipped": marker_skipped}
    if http is not None:
        try:
            http.close()
        except Exception:
            pass
    return result


@app.post("/api/sync")
def api_sync() -> dict[str, Any]:
    return run_sync()


@app.get("/api/projects")
def api_projects() -> dict[str, Any]:
    conn = store.connect(resolve_db_path())
    try:
        items = store.list_projects(conn)
    finally:
        conn.close()
    return {"projects": items, "count": len(items)}


@app.get("/api/sessions")
def api_sessions(
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    conn = store.connect(resolve_db_path())
    try:
        items = store.list_sessions(conn, project_id=project_id, limit=limit)
    finally:
        conn.close()
    return {"sessions": items, "count": len(items)}


@app.get("/api/transitions")
def api_transitions(
    limit: int = Query(default=100, ge=1, le=1000),
    kind: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    conn = store.connect(resolve_db_path())
    try:
        items = store.search_transitions(conn, session_id=session_id, kind=kind, limit=limit)
    finally:
        conn.close()
    return {"transitions": items, "count": len(items)}


@app.get("/api/history")
def api_history(
    session_id: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    conn = store.connect(resolve_db_path())
    try:
        items = store.search_transitions(
            conn, session_id=session_id, kind=kind, limit=limit
        )
    finally:
        conn.close()
    return {"transitions": items, "count": len(items), "session_id": session_id}


@app.get("/api/spec-check")
def api_spec_check() -> dict[str, Any]:
    # P4: 常に200。opencode到達不可でも警告1件+ok=falseで返す (health不変)。
    return spec_check.check_spec()


@app.get("/api/eventwatch")
def api_eventwatch() -> dict[str, Any]:
    """P5: event-subscription status (enabled/connected/triggers/syncs)."""
    try:
        debounce = float(config.EVENT_DEBOUNCE_SEC)
    except Exception:
        debounce = 2.0
    try:
        safety = float(config.EVENT_SAFETY_SEC)
    except Exception:
        safety = 60.0
    return {
        **dict(_event_status),
        "debounce_sec": debounce,
        "safety_sec": safety,
        "base_url": config.OPENCODE_BASE_URL,
    }


@app.get("/api/events")
async def api_events():
    queue: asyncio.Queue = asyncio.Queue()
    subscribers.add(queue)

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: sync\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            subscribers.discard(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def root() -> dict[str, Any]:
    return {"name": "oc-monitor backend", "health": "/api/health", "events": "/api/events"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=config.APP_PORT, reload=False)
