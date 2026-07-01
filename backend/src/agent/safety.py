"""Guardrails — the trust boundary for anything the agent touches on disk."""
from __future__ import annotations

import json
from pathlib import Path

from send2trash import send2trash

from agent.settings import app_data_dir, load_settings


class PathNotAllowed(Exception):
    """Raised when a path escapes the allowed roots or uses a forbidden form."""


def _is_within(child: Path, parent: Path) -> bool:
    # Case-insensitive containment for Windows. Compare resolved, normalized-case paths.
    try:
        c = str(child).casefold()
        p = str(parent).casefold()
    except Exception:
        return False
    return c == p or c.startswith(p.rstrip("\\/") + "\\") or c.startswith(p.rstrip("\\/") + "/")


def resolve_and_check(path: str, roots: list[str] | None = None) -> Path:
    if path is None:
        raise PathNotAllowed("no path given")
    raw = str(path)
    # Reject UNC and device/namespace prefixes outright — they bypass root logic.
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise PathNotAllowed(f"UNC/device path not allowed: {raw}")

    resolved = Path(raw).resolve()

    allowed = roots if roots is not None else load_settings().allowed_roots
    for r in allowed:
        root_resolved = Path(r).resolve()
        if _is_within(resolved, root_resolved):
            return resolved

    raise PathNotAllowed(f"path outside allowed roots: {resolved}")


def recycle_delete(path: Path) -> None:
    """Send a file to the Recycle Bin (recoverable), never a permanent delete."""
    send2trash(str(path))


def audit(entry: dict) -> None:
    """Append one JSON line to the persistent audit log in app-data."""
    line = json.dumps(entry, ensure_ascii=False)
    with (app_data_dir() / "audit.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
