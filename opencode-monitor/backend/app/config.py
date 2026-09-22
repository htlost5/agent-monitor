"""App configuration (env-overridable defaults)."""

import os

OPENCODE_BASE_URL = os.environ.get("OPENCODE_BASE_URL", "http://localhost:4096")
APP_PORT = int(os.environ.get("APP_PORT", "4100"))
DB_PATH = os.environ.get("DB_PATH", "backend/data/oc_monitor.db")
SYNC_MAX_PAGES = int(os.environ.get("SYNC_MAX_PAGES", "8"))
SYNC_TIMEOUT = float(os.environ.get("SYNC_TIMEOUT", "5.0"))

# TASK-3: marker-based immediate completion detection (180s idle fallback kept).
# Disable via MARKER_ENABLED=0 (perf rollback switch).
def _parse_marker_enabled(raw) -> int:
    """Parse MARKER_ENABLED: 0/false/no/off (case-insensitive) -> 0, else 1."""
    if isinstance(raw, bool):
        return 0 if raw is False else 1
    if isinstance(raw, int):
        return 0 if raw == 0 else 1
    s = str(raw).strip().lower() if raw is not None else ""
    if s in ("0", "false", "no", "off"):
        return 0
    if s in ("1", "true", "yes", "on"):
        return 1
    try:
        return 0 if int(s) == 0 else 1
    except (ValueError, TypeError):
        return 1


MARKER_ENABLED = _parse_marker_enabled(os.environ.get("MARKER_ENABLED", "1"))
MARKER_STRING = os.environ.get("MARKER_STRING", "__HERMES_TASK_DONE__")
MARKER_MSG_LIMIT = int(os.environ.get("MARKER_MSG_LIMIT", "10"))
MARKER_MAX_SESSIONS = int(os.environ.get("MARKER_MAX_SESSIONS", "20"))
try:
    MARKER_TIMEOUT = float(os.environ.get("MARKER_TIMEOUT", "3.0"))
except (ValueError, TypeError):
    MARKER_TIMEOUT = 3.0
if not (MARKER_TIMEOUT > 0):
    MARKER_TIMEOUT = 3.0

# P5 event-driven sync: backend subscribes to opencode /global/event (SSE)
# and runs debounced syncs instead of frontend 5s polling.
# Disable via EVENTWATCH_ENABLED=0 (rollback switch: frontend safety-net remains).
EVENTWATCH_ENABLED = _parse_marker_enabled(os.environ.get("EVENTWATCH_ENABLED", "1"))


def _parse_positive_float(raw: object, default: float) -> float:
    try:
        v = float(raw) if raw is not None else default
    except (ValueError, TypeError):
        return default
    return v if v > 0 else default


# Trailing-edge debounce for event-triggered syncs (streaming deltas coalesce).
EVENT_DEBOUNCE_SEC = _parse_positive_float(
    os.environ.get("EVENT_DEBOUNCE_SEC", "2.0"), 2.0
)


def _parse_safety_sec(raw: object) -> float:
    """Safety-net interval seconds. <=0 disables the safety task."""
    try:
        v = float(raw) if raw is not None else 60.0
    except (ValueError, TypeError):
        return 60.0
    return v if v > 0 else 0.0


EVENT_SAFETY_SEC = _parse_safety_sec(os.environ.get("EVENT_SAFETY_SEC", "60.0"))
