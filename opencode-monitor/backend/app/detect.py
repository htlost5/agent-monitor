"""P3 completion detection: pure functions only (no DB/IO here).

Kinds: created / updated / finished / anomaly.
All time comparisons are done in epoch seconds (float).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

FINISH_IDLE_SEC = int(os.environ.get("FINISH_IDLE_SEC", "180"))

# TASK-3: marker-based immediate completion (pure functions only).
MARKER = os.environ.get("MARKER_STRING", "__HERMES_TASK_DONE__")


def iter_text_parts(msg: Any):
    """Yield assistant text part bodies, tolerant to shape differences."""
    if not isinstance(msg, dict):
        return
    # Assistant-only: explicit non-assistant roles are skipped.
    role = msg.get("role")
    if role is None:
        info = msg.get("info")
        if isinstance(info, dict):
            role = info.get("role")
    if role is not None and role != "assistant":
        return
    parts: Any = msg.get("parts")
    if parts is None:
        parts = msg.get("content")
    if isinstance(parts, str):
        if parts:
            yield parts
        return
    if isinstance(parts, dict):
        parts = [parts]
    if isinstance(parts, list):
        for p in parts:
            if isinstance(p, str):
                if p:
                    yield p
            elif isinstance(p, dict):
                ptype = p.get("type")
                if ptype is not None and ptype != "text":
                    continue
                yielded = False
                for key in ("text", "content", "data", "value"):
                    v = p.get(key)
                    if isinstance(v, str):
                        if v:
                            yield v
                        yielded = True
                        break
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, str):
                                if item:
                                    yield item
                            elif isinstance(item, dict):
                                for k2 in ("text", "content"):
                                    vv = item.get(k2)
                                    if isinstance(vv, str) and vv:
                                        yield vv
                                        break
                        yielded = True
                        break
                if yielded:
                    continue
        return
    # Fallback: flat text fields when no parts/content shape.
    for key in ("text", "body"):
        v = msg.get(key)
        if isinstance(v, str) and v:
            yield v
            return


def has_marker(messages: Any, marker: Optional[str] = None) -> bool:
    """True when any assistant text part has a line exactly equal to marker."""
    mk = marker if marker is not None else MARKER
    if not isinstance(messages, list):
        return False
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        try:
            texts = iter_text_parts(msg)
        except Exception:
            continue
        for text in texts:
            if not isinstance(text, str):
                continue
            for line in text.splitlines():
                if line.strip() == mk:
                    return True
    return False


def is_active(
    updated_epoch: Optional[float],
    now_epoch: float,
    idle_sec: float = FINISH_IDLE_SEC,
) -> bool:
    """Active = updated recently (< idle_sec ago). None timestamp -> False."""
    if updated_epoch is None:
        return False
    try:
        return (float(now_epoch) - float(updated_epoch)) < float(idle_sec)
    except (TypeError, ValueError):
        return False


def to_epoch(v: Any) -> Optional[float]:
    """Normalize ISO string / epoch-ms / epoch-sec to epoch seconds. None if unknown."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 1e12:  # epoch-ms
            ts /= 1000.0
        elif ts > 1e11:  # unlikely range: treat as ms too
            ts /= 1000.0
        return ts
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # plain numeric string: epoch ms or sec
        try:
            num = float(s)
            return to_epoch(num)
        except ValueError:
            pass
        iso = s.replace("Z", "+00:00")
        # "+0000" -> "+00:00" (store._now style)
        if len(iso) >= 5 and iso[-5] in ("+", "-") and iso[-2:].isdigit():
            iso = iso[:-2] + ":" + iso[-2:]
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None
    return None


def is_idle(updated_epoch: Optional[float], now_epoch: float, finish_idle_sec: float) -> bool:
    if updated_epoch is None:
        return False
    return (now_epoch - updated_epoch) >= finish_idle_sec


def diff_snapshots(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    now_epoch: float,
    finish_idle_sec: float = FINISH_IDLE_SEC,
) -> list[dict[str, Any]]:
    """Diff old/new {session_id: updated_at} snapshots (epoch comparison).

    Emits dicts: {session_id, kind, old_updated_at, new_updated_at, detail}.
    - created: id in new, not in old
    - updated: both present, new epoch > old epoch
    - finished: new epoch idle (>= finish_idle_sec behind now)
    - anomaly: clock rollback (new < old), unparseable/missing timestamp
    """
    events: list[dict[str, Any]] = []
    for sid, new_ts in new.items():
        new_ep = to_epoch(new_ts)
        if sid not in old:
            events.append(
                {"session_id": sid, "kind": "created",
                 "old_updated_at": None, "new_updated_at": _s(new_ts), "detail": None}
            )
            if new_ep is None:
                events.append(
                    {"session_id": sid, "kind": "anomaly",
                     "old_updated_at": None, "new_updated_at": _s(new_ts),
                     "detail": "unparseable updated_at on create"}
                )
            elif is_idle(new_ep, now_epoch, finish_idle_sec):
                events.append(
                    {"session_id": sid, "kind": "finished",
                     "old_updated_at": None, "new_updated_at": _s(new_ts),
                     "detail": f"idle>={int(finish_idle_sec)}s: 完了の可能性 (長考runの誤検知あり得る)"}
                )
            continue
        old_ts = old.get(sid)
        old_ep = to_epoch(old_ts)
        if new_ep is None or old_ep is None:
            # null->value counts as update; otherwise anomaly
            if old_ep is None and new_ep is not None:
                events.append(
                    {"session_id": sid, "kind": "updated",
                     "old_updated_at": _s(old_ts), "new_updated_at": _s(new_ts), "detail": None}
                )
            elif new_ep is None and old_ep is not None:
                events.append(
                    {"session_id": sid, "kind": "anomaly",
                     "old_updated_at": _s(old_ts), "new_updated_at": _s(new_ts),
                     "detail": "updated_at became unparseable"}
                )
        elif new_ep > old_ep:
            events.append(
                {"session_id": sid, "kind": "updated",
                 "old_updated_at": _s(old_ts), "new_updated_at": _s(new_ts), "detail": None}
            )
        elif new_ep < old_ep:
            events.append(
                {"session_id": sid, "kind": "anomaly",
                 "old_updated_at": _s(old_ts), "new_updated_at": _s(new_ts),
                 "detail": "updated_at moved backwards"}
            )
        if new_ep is not None and is_idle(new_ep, now_epoch, finish_idle_sec):
            # freshly updated rows have now-new_ep ~ 0, so no false positive
            events.append(
                {"session_id": sid, "kind": "finished",
                 "old_updated_at": _s(old_ts), "new_updated_at": _s(new_ts),
                 "detail": f"idle>={int(finish_idle_sec)}s: 完了の可能性 (長考runの誤検知あり得る)"}
            )
    return events


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v if isinstance(v, str) else str(v)
