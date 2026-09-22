"""P4 spec drift check: fetch opencode /doc (OpenAPI 3.1 JSON) and compare endpoints.

- Snapshot: backend/data/spec_snapshot.json (initial generation on first use).
- /doc unreachable -> warnings 1件 + ok=false, caller must still return HTTP 200.
- Pure helpers (extract_paths / diff_paths) are unit-testable without network.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx

# oc-monitor depends on these opencode endpoints (canonical paths).
REQUIRED_ENDPOINTS = ["/global/health", "/project", "/session"]

SNAPSHOT_REL = Path("backend/data/spec_snapshot.json")


def resolve_snapshot_path() -> Path:
    p = SNAPSHOT_REL
    if p.is_absolute():
        return p
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / p


def resolve_base_url(base_url: Optional[str] = None) -> str:
    if base_url:
        return base_url.rstrip("/")
    try:
        from . import config

        return str(config.OPENCODE_BASE_URL).rstrip("/")
    except Exception:
        return "http://localhost:4096"


def extract_paths(doc: Any) -> list[str]:
    """Extract sorted OpenAPI path keys from a /doc payload. Empty-safe."""
    if not isinstance(doc, dict):
        return []
    paths = doc.get("paths")
    if not isinstance(paths, dict):
        return []
    out = [k for k in paths.keys() if isinstance(k, str)]
    return sorted(out)


def diff_paths(snapshot_paths: list[str], live_paths: list[str]) -> dict[str, list[str]]:
    """Compare endpoint existence. Returns {missing, extra} (both sorted)."""
    snap = set(snapshot_paths)
    live = set(live_paths)
    missing = sorted(snap - live)
    extra = sorted(live - snap)
    return {"missing": missing, "extra": extra}


def load_snapshot(path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    p = path or resolve_snapshot_path()
    try:
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_snapshot(
    paths: list[str],
    path: Optional[Path] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    p = path or resolve_snapshot_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "opencode /doc (OpenAPI 3.1 JSON)",
        "openapi": "3.1.0",
        "endpoint_count": len(paths),
        "paths": sorted(paths),
        "required": list(REQUIRED_ENDPOINTS),
    }
    if extra:
        payload.update(extra)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def ensure_snapshot(
    path: Optional[Path] = None, live_paths: Optional[list[str]] = None
) -> tuple[dict[str, Any], bool]:
    """Return (snapshot, created). Creates initial snapshot if missing.

    If live_paths is given, snapshot from it; otherwise from REQUIRED fallback.
    """
    snap = load_snapshot(path)
    if snap is not None and isinstance(snap.get("paths"), list):
        return snap, False
    seed = list(live_paths) if live_paths is not None else list(REQUIRED_ENDPOINTS)
    created = save_snapshot(sorted(seed), path)
    return created, True


def fetch_doc(base_url: Optional[str] = None, timeout: float = 5.0) -> Any:
    """GET {base}/doc (OpenAPI JSON). Raises on network/HTTP error."""
    base = resolve_base_url(base_url)
    with httpx.Client(base_url=base, timeout=timeout) as client:
        resp = client.get("/doc")
        resp.raise_for_status()
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return None


def check_spec(
    base_url: Optional[str] = None,
    timeout: float = 5.0,
    snapshot_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Compare live /doc endpoints against snapshot. Never raises.

    - Reachable: missing (snapshot-required drift) -> ok=false + warnings.
    - Unreachable: warnings exactly 1件 + ok=false + reachable=false (HTTP 200は呼出側で).
    """
    snap_path = snapshot_path or resolve_snapshot_path()

    # 1. fetch live /doc
    try:
        doc = fetch_doc(base_url, timeout=timeout)
    except Exception as e:
        # 到達不可は警告1件に留める (P4設計)
        ensure_snapshot(snap_path)  # 初回生成だけは保証
        snap = load_snapshot(snap_path) or {}
        return {
            "ok": False,
            "reachable": False,
            "warnings": [f"opencode /doc unreachable (treated as warning): {type(e).__name__}"],
            "missing": [],
            "extra": [],
            "endpoint_count": 0,
            "snapshot_endpoints": len(snap.get("paths", []) or []),
            "required": list(REQUIRED_ENDPOINTS),
        }
    if doc is None:
        ensure_snapshot(snap_path)
        snap = load_snapshot(snap_path) or {}
        return {
            "ok": False,
            "reachable": False,
            "warnings": ["opencode /doc empty response (treated as warning)"],
            "missing": [],
            "extra": [],
            "endpoint_count": 0,
            "snapshot_endpoints": len(snap.get("paths", []) or []),
            "required": list(REQUIRED_ENDPOINTS),
        }

    live_paths = extract_paths(doc)
    snapshot, created = ensure_snapshot(snap_path, live_paths)
    snapshot_paths = snapshot.get("paths", []) if isinstance(snapshot, dict) else []
    if not isinstance(snapshot_paths, list):
        snapshot_paths = []

    # required endpoints の有無が主比較。その上で snapshot drift も検出。
    required_missing = [p for p in REQUIRED_ENDPOINTS if p not in set(live_paths)]
    drift = diff_paths([str(p) for p in snapshot_paths], live_paths)
    # snapshotに無いrequiredはdrift missingに含めないため、required_missingを優先表示
    missing = required_missing + [p for p in drift["missing"] if p not in required_missing]

    warnings: list[str] = []
    if created:
        warnings.append("spec snapshot created (initial)")
    for p in required_missing:
        warnings.append(f"required endpoint missing in /doc: {p}")
    for p in drift["missing"]:
        if p not in required_missing:
            warnings.append(f"endpoint disappeared vs snapshot: {p}")
    # extra は情報扱い: 多すぎるとノイズなので件数のみ
    if drift["extra"]:
        warnings.append(f"{len(drift['extra'])} new endpoint(s) vs snapshot (info)")

    ok = len(missing) == 0
    return {
        "ok": ok,
        "reachable": True,
        "warnings": warnings,
        "missing": missing,
        "extra": drift["extra"][:50],
        "endpoint_count": len(live_paths),
        "snapshot_endpoints": len(snapshot_paths),
        "required": list(REQUIRED_ENDPOINTS),
        "snapshot_created": created,
    }
