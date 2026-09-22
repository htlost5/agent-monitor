"""TASK-3 verification: marker-based immediate completion detection.

Runs without a live OpenCode server (fake clients + temp DB + source checks):
[1] config MARKER_* defaults (ENABLED=1, STRING, MSG_LIMIT=10, MAX=20, TIMEOUT=3.0)
[2] detect pure funcs: MARKER / iter_text_parts / has_marker / is_active (+diff_snapshots smoke)
[3] opencode_client.get_session_messages (path/params/coerce + exception propagates)
[4] api_sync marker flow (hit->finished合成, dedup±1s, failure->warnings, disabled, idle-skip, marker field)
[5] frontend marker priority + wording branch
[6] forbidden files unchanged (store/spec_check/lib without marker; existing verifies intact)
"""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[0]
sys.path.insert(0, str(BACKEND))

from app import config, detect  # noqa: E402


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _check_config() -> None:
    assert hasattr(config, "MARKER_ENABLED"), "config.MARKER_ENABLED missing"
    assert hasattr(config, "MARKER_STRING"), "config.MARKER_STRING missing"
    assert hasattr(config, "MARKER_MSG_LIMIT"), "config.MARKER_MSG_LIMIT missing"
    assert hasattr(config, "MARKER_MAX_SESSIONS"), "config.MARKER_MAX_SESSIONS missing"
    assert hasattr(config, "MARKER_TIMEOUT"), "config.MARKER_TIMEOUT missing"
    assert int(config.MARKER_ENABLED) == 1 or bool(config.MARKER_ENABLED) is True, \
        f"MARKER_ENABLED default must be 1/truthy (got {config.MARKER_ENABLED!r})"
    assert str(config.MARKER_STRING) == "__HERMES_TASK_DONE__", \
        f"MARKER_STRING={config.MARKER_STRING!r}"
    assert int(config.MARKER_MSG_LIMIT) == 10, f"MARKER_MSG_LIMIT={config.MARKER_MSG_LIMIT!r}"
    assert int(config.MARKER_MAX_SESSIONS) == 20, \
        f"MARKER_MAX_SESSIONS={config.MARKER_MAX_SESSIONS!r}"
    assert abs(float(config.MARKER_TIMEOUT) - 3.0) < 1e-9, \
        f"MARKER_TIMEOUT={config.MARKER_TIMEOUT!r}"
    # [中] disable parser: 0/false/no/off (case-insensitive) -> 0, canonical notation is 0
    _parse = getattr(config, "_parse_marker_enabled", None)
    assert callable(_parse), "config._parse_marker_enabled missing"
    for _v in ("0", "false", "False", "FALSE", "no", "No", "NO",
               "off", "Off", "OFF", "  off  ", "  False  "):
        assert _parse(_v) == 0, f"parser must map {_v!r} to 0"
    assert _parse("1") == 1, "parser must map '1' to 1"
    assert _parse(0) == 0 and _parse(1) == 1, "parser int handling broken"
    print("[1/6] config MARKER_* defaults OK")


def _check_detect() -> None:
    assert getattr(detect, "MARKER", None) == "__HERMES_TASK_DONE__", \
        f"detect.MARKER={getattr(detect, 'MARKER', None)!r}"
    # iter_text_parts: tolerant shapes, assistant-only
    a1 = {"role": "assistant", "parts": [{"type": "text", "text": "hello"}]}
    assert list(detect.iter_text_parts(a1)) == ["hello"], "basic parts.text failed"
    a2 = {"role": "assistant", "parts": [{"type": "text", "content": "via-content"}]}
    assert list(detect.iter_text_parts(a2)) == ["via-content"], "parts.content failed"
    a3 = {"role": "assistant", "content": "flat-string"}
    assert list(detect.iter_text_parts(a3)) == ["flat-string"], "flat content failed"
    u1 = {"role": "user", "parts": [{"type": "text", "text": "__HERMES_TASK_DONE__"}]}
    assert list(detect.iter_text_parts(u1)) == [], "user role must be skipped"
    tool = {"role": "assistant", "parts": [{"type": "tool", "text": "skip-me"}]}
    assert list(detect.iter_text_parts(tool)) == [], "non-text part must be skipped"
    assert list(detect.iter_text_parts({"role": "assistant", "parts": []})) == []
    assert list(detect.iter_text_parts(None)) == []  # type: ignore[arg-type]
    assert list(detect.iter_text_parts("str")) == []  # type: ignore[arg-type]

    # has_marker: line-strip exact match
    mk = "__HERMES_TASK_DONE__"
    hit = [{"role": "assistant", "parts": [{"type": "text", "text": f"done\n  {mk}  \n"}]}]
    assert detect.has_marker(hit) is True, "strip-exact hit failed"
    miss_embed = [{"role": "assistant", "parts": [{"type": "text", "text": f"prefix {mk} suffix"}]}]
    assert detect.has_marker(miss_embed) is False, "embedded line must NOT match"
    miss_user = [{"role": "user", "parts": [{"type": "text", "text": mk}]}]
    assert detect.has_marker(miss_user) is False, "user marker must NOT match"
    assert detect.has_marker([]) is False
    assert detect.has_marker([{"role": "assistant", "parts": [{"type": "text", "text": "plain"}]}]) is False
    multi = [
        {"role": "assistant", "parts": [{"type": "text", "text": "thinking..."}]},
        {"role": "assistant", "parts": [{"type": "text", "text": f"result\n{mk}"}]},
    ]
    assert detect.has_marker(multi) is True, "multi-message hit failed"

    # is_active
    now = time.time()
    assert detect.is_active(now - 10, now, 180) is True
    assert detect.is_active(now - 600, now, 180) is False
    assert detect.is_active(None, now, 180) is False

    # diff_snapshots unchanged smoke (fresh -> created only, no finished)
    fresh = _iso(now - 10)
    ev = detect.diff_snapshots({}, {"a": fresh}, now)
    assert any(e["kind"] == "created" for e in ev), ev
    assert not any(e["kind"] == "finished" for e in ev), ev
    print("[2/6] detect MARKER/iter_text_parts/has_marker/is_active OK")


def _check_client() -> None:
    from app.opencode_client import OpenCodeClient

    assert hasattr(OpenCodeClient, "get_session_messages"), "get_session_messages missing"
    import inspect as _inspect
    _sig = _inspect.signature(OpenCodeClient.get_session_messages)
    assert "timeout" in _sig.parameters, \
        "get_session_messages must accept timeout (MARKER_TIMEOUT per-request)"
    calls: dict = {}

    class FakeHTTP:
        def get(self, path: str, params: dict | None = None, timeout=None):
            calls["path"] = path
            calls["params"] = params
            calls["timeout"] = timeout

            class R:
                content = b'{"x": 1}'

                def raise_for_status(self):
                    pass

                def json(self):
                    return [{"role": "assistant", "parts": [{"type": "text", "text": "hi"}]}]

            return R()

    c = OpenCodeClient("http://localhost:4096", client=FakeHTTP())  # type: ignore[arg-type]
    out = c.get_session_messages("ses123", limit=10)
    assert isinstance(out, list) and out and out[0].get("role") == "assistant", out
    assert calls.get("path") == "/session/ses123/message", calls
    assert (calls.get("params") or {}).get("limit") == 10, calls

    # timeout適用: per-request overrideがHTTP層へ転送されること
    out2 = c.get_session_messages("ses123", limit=10, timeout=3.0)
    assert calls.get("path") == "/session/ses123/message", calls
    assert abs(float(calls.get("timeout")) - 3.0) < 1e-9, \
        f"timeout not forwarded to HTTP layer: {calls!r}"

    class BoomHTTP:
        def get(self, path: str, params: dict | None = None, timeout=None):
            raise RuntimeError("net-down")

    c2 = OpenCodeClient("http://localhost:4096", client=BoomHTTP())  # type: ignore[arg-type]
    try:
        c2.get_session_messages("s", limit=10)
    except RuntimeError:
        pass
    else:
        raise AssertionError("get_session_messages must propagate exceptions")
    print("[3/6] opencode_client.get_session_messages OK")


def _check_api_sync() -> None:
    import app.main as main_mod
    from fastapi.testclient import TestClient

    RealClient = main_mod.OpenCodeClient
    orig_db = config.DB_PATH
    orig_enabled = config.MARKER_ENABLED
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "verify_marker.db")
        config.DB_PATH = db

        now = time.time()
        fresh_iso = _iso(now - 5)

        state: dict = {"mode": "hit", "fetch_calls": []}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def list_projects(self):
                return []

            def list_sessions(self, max_pages: int = 8):
                return [{"id": "s-active", "updatedAt": fresh_iso}]

            def get_session_messages(self, session_id: str, limit: int = 10,
                                       timeout: float | None = None):
                state["fetch_calls"].append((session_id, limit))
                state.setdefault("timeouts", []).append(timeout)
                assert limit == int(config.MARKER_MSG_LIMIT)
                # [高] MARKER_TIMEOUTがper-request適用されること
                assert timeout is not None, "marker fetch must pass timeout=MARKER_TIMEOUT"
                assert abs(float(timeout) - float(config.MARKER_TIMEOUT)) < 1e-9 or (
                    0 < float(timeout) <= float(config.MARKER_TIMEOUT)
                ), f"marker timeout must be MARKER_TIMEOUT ({config.MARKER_TIMEOUT!r}) or remaining budget, got {timeout!r}"
                if state["mode"] == "boom":
                    raise RuntimeError("msg-down")
                if state["mode"] == "hit":
                    return [{"role": "assistant",
                             "parts": [{"type": "text",
                                        "text": "work done\n__HERMES_TASK_DONE__\n"}]}]
                return [{"role": "assistant",
                         "parts": [{"type": "text", "text": "still working"}]}]

        main_mod.OpenCodeClient = FakeClient  # type: ignore[assignment]
        try:
            client = TestClient(main_mod.app)
            # 4a: hit -> finished synthesized with marker detail + marker field
            state["mode"] = "hit"
            state["fetch_calls"] = []
            state["timeouts"] = []
            r = client.post("/api/sync")
            assert r.status_code == 200, r.text
            body = r.json()
            assert "marker" in body, body
            assert body["marker"]["checked"] == 1, body["marker"]
            assert body["marker"]["hit"] == 1, body["marker"]
            assert state["timeouts"], "marker fetch must apply timeout"
            assert all(
                t is not None and 0 < float(t) <= float(config.MARKER_TIMEOUT) + 1e-9
                for t in state["timeouts"]
            ), f"timeouts must be MARKER_TIMEOUT per-request (or remaining budget): {state['timeouts']!r}"
            trans = body.get("transitions") or []
            fins = [t for t in trans if t.get("kind") == "finished"
                    and t.get("session_id") == "s-active"]
            assert len(fins) == 1, trans
            assert "marker:__HERMES_TASK_DONE__" in (fins[0].get("detail") or ""), fins[0]
            assert "(即時確定)" in (fins[0].get("detail") or ""), fins[0]

            # 4b: second sync same stamp -> dedup (no repeat finished)
            state["fetch_calls"] = []
            r2 = client.post("/api/sync")
            assert r2.status_code == 200, r2.text
            b2 = r2.json()
            assert b2["marker"]["checked"] == 1, b2["marker"]
            assert b2["marker"]["hit"] == 0, b2["marker"]
            t2 = b2.get("transitions") or []
            assert not [t for t in t2 if t.get("kind") == "finished"
                        and t.get("session_id") == "s-active"], t2

            # 4c: failure -> warnings化, no crash
            # use a fresh session id so dedup does not mask the failure path
            class FakeClient2(FakeClient):
                def list_sessions(self, max_pages: int = 8):
                    return [{"id": "s-boom", "updatedAt": _iso(time.time() - 5)}]

            main_mod.OpenCodeClient = FakeClient2  # type: ignore[assignment]
            state["mode"] = "boom"
            state["fetch_calls"] = []
            rb = client.post("/api/sync")
            assert rb.status_code == 200, rb.text
            bb = rb.json()
            assert bb["marker"]["checked"] == 0, bb["marker"]
            assert bb["marker"]["skipped"] >= 1, bb["marker"]
            assert any("marker fetch failed" in w for w in (bb.get("warnings") or [])), bb

            # 4d: MARKER_ENABLED=0 -> no fetch, skipped counts active
            main_mod.OpenCodeClient = FakeClient  # type: ignore[assignment]
            config.MARKER_ENABLED = 0
            state["mode"] = "hit"
            state["fetch_calls"] = []
            rd = client.post("/api/sync")
            assert rd.status_code == 200, rd.text
            bd = rd.json()
            assert bd["marker"]["checked"] == 0 and bd["marker"]["hit"] == 0, bd["marker"]
            assert state["fetch_calls"] == [], "disabled must not fetch messages"
            config.MARKER_ENABLED = orig_enabled

            # 4e: idle session is not polled
            class FakeIdle(FakeClient):
                def list_sessions(self, max_pages: int = 8):
                    return [{"id": "s-idle", "updatedAt": _iso(time.time() - 600)}]

            main_mod.OpenCodeClient = FakeIdle  # type: ignore[assignment]
            state["fetch_calls"] = []
            ri = client.post("/api/sync")
            assert ri.status_code == 200, ri.text
            bi = ri.json()
            assert bi["marker"]["checked"] == 0, bi["marker"]
        finally:
            main_mod.OpenCodeClient = RealClient
            config.DB_PATH = orig_db
            config.MARKER_ENABLED = orig_enabled
    print("[4/6] api_sync marker poll+synth+dedup+warnings+disabled OK")


def _check_frontend() -> None:
    fe = REPO / "frontend" / "src"
    hook = (fe / "hooks" / "useTransitionNotify.ts").read_text(encoding="utf-8")
    assert "marker:" in hook, "useTransitionNotify must prioritize marker detail"
    assert hook.count("find") >= 2, "lastFinished must try marker-first then fallback"
    assert 't.kind === "finished"' in hook or "t.kind==='finished'" in hook.replace(" ", ""), \
        "lastFinished must filter kind finished"
    app_tsx = (fe / "App.tsx").read_text(encoding="utf-8")
    assert "marker:" in app_tsx, "App.tsx must branch on marker detail"
    assert "マーカー確定" in app_tsx, "App.tsx marker wording missing"
    assert "完了の可能性" in app_tsx, "App.tsx must keep legacy idle wording"
    print("[5/6] frontend marker priority + wording branch OK")


def _check_forbidden() -> None:
    for rel in ("backend/app/store.py", "backend/app/spec_check.py", "frontend/src/lib.ts"):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "marker" not in text.lower(), f"{rel} must stay unchanged (marker found)"
    for rel in ("backend/scripts/verify_p1.py", "backend/scripts/verify_p3.py",
                "backend/scripts/verify_p4.py"):
        p = REPO / rel
        assert p.exists(), f"{rel} missing"
        text = p.read_text(encoding="utf-8")
        assert "marker" not in text.lower(), f"{rel} must stay unchanged (marker found)"
    print("[6/6] forbidden files unchanged OK")


def main() -> int:
    _check_config()
    _check_detect()
    _check_client()
    _check_api_sync()
    _check_frontend()
    _check_forbidden()
    print("marker verify: ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
