"""Chat session registry: titles + activity steps per thread.

The conversation messages themselves live in checkpoints.db (LangGraph's
checkpointer); this file only records which threads exist, their titles,
and the activity-log steps so the UI can restore them.
"""
from __future__ import annotations

import json
import time

from agent.settings import app_data_dir

MAX_STEPS = 300  # per session; the activity log is a trail, not an archive


def _path():
    return app_data_dir() / "sessions.json"


def _load() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(sessions: list[dict]) -> None:
    _path().write_text(json.dumps(sessions, ensure_ascii=False, indent=1), encoding="utf-8")


def list_sessions() -> list[dict]:
    """Newest first, without the steps payload (kept light for the list view)."""
    out = [{k: s[k] for k in ("id", "title", "updated")} for s in _load()]
    return sorted(out, key=lambda s: s["updated"], reverse=True)


def ensure_session(thread_id: str, title: str) -> None:
    """Create the session on first message; never overwrite an existing title."""
    sessions = _load()
    for s in sessions:
        if s["id"] == thread_id:
            s["updated"] = time.time()
            _save(sessions)
            return
    sessions.append(
        {"id": thread_id, "title": title[:60], "updated": time.time(), "steps": []}
    )
    _save(sessions)


def append_step(thread_id: str, step: dict) -> None:
    sessions = _load()
    for s in sessions:
        if s["id"] == thread_id:
            s["steps"] = (s.get("steps", []) + [step])[-MAX_STEPS:]
            s["updated"] = time.time()
            _save(sessions)
            return
    # Steps before the session exists (pre-first-message) are dropped — fine.


def get_steps(thread_id: str) -> list[dict]:
    for s in _load():
        if s["id"] == thread_id:
            return s.get("steps", [])
    return []
