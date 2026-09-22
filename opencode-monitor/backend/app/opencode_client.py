"""Minimal httpx client for the local OpenCode server.

Endpoints (relative to OPENCODE_BASE_URL):
- GET /global/health  (health check)
- GET /project        (project list)
- GET /api/session    (web UI session list, primary)
- GET /session        (legacy fallback, only when webui is empty/raises)
"""

from __future__ import annotations

from typing import Any

import httpx


def _coerce_list(payload: Any) -> list[dict[str, Any]]:
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


class OpenCodeClient:
    """Single httpx.Client reused for one sync round.

    `client` may be injected (shared per-sync); otherwise an internal
    client is created and owned by this instance.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            try:
                self._client.close()
            except Exception:
                pass

    def __enter__(self) -> OpenCodeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        import warnings

        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = float(timeout)
        resp = self._client.get(path, params=params, **kwargs)
        resp.raise_for_status()
        if not resp.content:
            warnings.warn(f"opencode empty response: GET {path} {params or {}}")
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get_health(self) -> Any:
        """GET /global/health"""
        return self._get("/global/health")

    def list_projects(self) -> Any:
        """GET /project"""
        return self._get("/project")

    def list_session_page(self, limit: int = 100, start: int = 0) -> Any:
        """GET /session single page (legacy fallback path)."""
        return self._get("/session", params={"limit": limit, "start": start})

    def list_sessions_webui(self, max_pages: int = 8) -> list[dict[str, Any]]:
        """GET /api/session cursor walk (web UI endpoint, primary).

        Item shape differs: {id, projectID, agent, model{id}, cost, tokens,
        time{created,updated}, title, location{directory}}.
        """
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        cursor: Any = None
        for _ in range(max_pages):
            params = {"cursor": cursor} if cursor else None
            payload = self._get("/api/session", params=params)
            page = _coerce_list(payload)
            if not page:
                break
            fresh = False
            for p in page:
                pid = p.get("id")
                if isinstance(pid, str):
                    if pid not in seen:
                        seen.add(pid)
                        items.append(p)
                        fresh = True
                else:
                    items.append(p)
                    fresh = True
            cur = payload.get("cursor") if isinstance(payload, dict) else None
            nxt: Any = None
            if isinstance(cur, dict):
                for k in ("next", "after", "nextCursor"):
                    if cur.get(k):
                        nxt = cur.get(k)
                        break
            elif isinstance(cur, str) and cur:
                nxt = cur
            if not nxt or not fresh:
                break
            cursor = nxt
        return items

    def list_sessions_legacy(
        self, page_limit: int = 100, max_pages: int = 8
    ) -> list[dict[str, Any]]:
        """GET /session simple offset loop (fallback only, no probe/escalation)."""
        import warnings

        by_id: dict[str, dict[str, Any]] = {}
        no_id: list[dict[str, Any]] = []
        start = 0
        for _ in range(max_pages):
            payload = self.list_session_page(limit=page_limit, start=start)
            if payload is None:
                if not by_id and not no_id and start == 0:
                    warnings.warn("opencode sessions empty response (treated as warning)")
                break
            page = _coerce_list(payload)
            if not page:
                if not by_id and not no_id and start == 0:
                    warnings.warn("opencode sessions empty list (treated as warning)")
                break
            for p in page:
                pid = p.get("id")
                if isinstance(pid, str):
                    by_id[pid] = p
                else:
                    no_id.append(p)
            if len(page) < page_limit:
                break
            start += len(page)
        return list(by_id.values()) + no_id

    def list_sessions(
        self, page_limit: int = 100, max_pages: int = 8
    ) -> list[dict[str, Any]]:
        """Primary: webui /api/session. Legacy /session only on empty/exception."""
        try:
            webui = self.list_sessions_webui(max_pages=max_pages)
        except Exception:
            webui = []
        if webui:
            return webui
        # Fallback: legacy returns []/raises -> caller treats as warning, not crash.
        try:
            return self.list_sessions_legacy(page_limit=page_limit, max_pages=max_pages)
        except Exception:
            return webui

    def get_session_messages(
        self, session_id: str, limit: int = 10, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """GET /session/{id}/message (recent messages, for marker detection).

        `timeout` is a per-request override (seconds). When None, the shared
        client's default timeout applies. Marker polling passes MARKER_TIMEOUT
        here so one slow session cannot stall the whole sync.
        Exceptions propagate to the caller (api_sync converts them to warnings).
        """
        payload = self._get(
            f"/session/{session_id}/message", params={"limit": limit}, timeout=timeout
        )
        return _coerce_list(payload)
