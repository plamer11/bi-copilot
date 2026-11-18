
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from app.config import settings

_LOCK = threading.Lock()
_PATH = Path(settings.audit_log_path)


def log_event(session_id: str, event_type: str, **payload) -> None:
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session_id": session_id,
        "event": event_type,
        **payload,
    }
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str)
    with _LOCK:
        with _PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_events(limit: int = 100, session_id: str | None = None) -> list[dict]:
    if not _PATH.exists():
        return []
    with _PATH.open("r", encoding="utf-8") as f:
        lines = f.readlines()[-500:]
    events = []
    for ln in lines:
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if session_id and e.get("session_id") != session_id:
            continue
        events.append(e)
    return events[-limit:]


def stats() -> dict:
    events = read_events(limit=5000)
    out = {
        "total_events": len(events),
        "by_type": {},
        "blocked": 0,
        "approval_required": 0,
        "repairs": 0,
    }
    for e in events:
        t = e.get("event", "unknown")
        out["by_type"][t] = out["by_type"].get(t, 0) + 1
        if t == "guard_blocked":
            out["blocked"] += 1
        if t == "approval_required":
            out["approval_required"] += 1
        if t == "repair":
            out["repairs"] += 1
    return out
