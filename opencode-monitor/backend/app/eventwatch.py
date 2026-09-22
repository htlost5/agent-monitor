"""P5 event-driven sync trigger: subscribe to opencode /global/event (SSE).

Design:
- The backend holds ONE long-lived subscription (single-worker premise;
  uvicorn runs with reload=False, one process).
- Relevant opencode events only *request* a sync; the caller (main.py)
  debounces + coalesces requests, so streaming deltas cannot cause a
  sync storm.
- Disconnects reconnect with backoff; every (re)connect schedules a
  catch-up sync via the "reconnected" trigger so missed events cannot
  silently desync the DB.
- server.heartbeat lines only prove the stream is alive (a read timeout
  on total silence forces reconnect + catch-up).

Wire shape of /global/event (opencode 1.18.x, verified live):
  data: {"directory": ..., "project": ...,
         "payload": {"id": "evt_...", "type": "session.created",
                     "properties": {...}}}
plus duplicate wrapper lines {"type": "sync", "syncEvent": {...}} which are
ignored (the real event arrives as its own data line).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, MutableMapping, Optional

import httpx

# Never sync triggers; heartbeats only prove liveness, "sync" is a duplicate
# wrapper of an event that arrives separately.
IGNORED_TYPES = frozenset({"server.connected", "server.heartbeat", "sync"})

RECONNECT_BASE_SEC = 1.0
RECONNECT_MAX_SEC = 30.0
# No data line at all for this long -> drop + reconnect (heartbeats normally
# arrive far more often; verified ~seconds apart on 1.18.31).
READ_TIMEOUT_SEC = 45.0
CONNECT_TIMEOUT_SEC = 5.0


def parse_event_type(line: str) -> Optional[str]:
    """Extract the opencode event type from one SSE line. None if not an event."""
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s.startswith("data:"):
        return None
    try:
        obj = json.loads(s[5:])
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        payload = obj
    t = payload.get("type")
    if isinstance(t, str) and t:
        return t
    return None


def is_sync_trigger(event_type: Optional[str]) -> bool:
    """True for event types that should request a backend sync."""
    return bool(event_type) and event_type not in IGNORED_TYPES


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def watch_forever(
    base_url: str,
    on_trigger: Callable[[str], None],
    status: MutableMapping[str, Any],
) -> None:
    """Hold the /global/event subscription until cancelled.

    on_trigger(type) is invoked synchronously for every relevant event and
    once with "reconnected" after each (re)connect for catch-up.
    status dict is updated in place (connected / reconnects / last_event_*).
    """
    base = base_url.rstrip("/")
    backoff = RECONNECT_BASE_SEC
    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT_SEC,
        read=READ_TIMEOUT_SEC,
        write=CONNECT_TIMEOUT_SEC,
        pool=CONNECT_TIMEOUT_SEC,
    )
    while True:
        try:
            async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
                async with client.stream("GET", "/global/event") as resp:
                    resp.raise_for_status()
                    status["connected"] = True
                    status["connected_at"] = _utcnow_iso()
                    status["last_error"] = None
                    backoff = RECONNECT_BASE_SEC
                    try:
                        on_trigger("reconnected")
                    except Exception:
                        pass
                    async for line in resp.aiter_lines():
                        if not line or not line.strip():
                            continue
                        etype = parse_event_type(line)
                        if etype is None:
                            continue
                        status["last_event_type"] = etype
                        status["last_event_at"] = _utcnow_iso()
                        if not is_sync_trigger(etype):
                            continue
                        status["triggers"] = int(status.get("triggers", 0)) + 1
                        status["last_trigger"] = etype
                        status["last_trigger_at"] = _utcnow_iso()
                        try:
                            on_trigger(etype)
                        except Exception:
                            continue
        except asyncio.CancelledError:
            status["connected"] = False
            raise
        except Exception as e:
            status["connected"] = False
            status["last_error"] = f"{type(e).__name__}: {e}"
            status["reconnects"] = int(status.get("reconnects", 0)) + 1
            try:
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                raise
            backoff = min(backoff * 2.0, RECONNECT_MAX_SEC)
