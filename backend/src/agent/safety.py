"""Guardrails — the trust boundary for anything the agent touches on disk."""
from __future__ import annotations

import json
import re
from pathlib import Path

from send2trash import send2trash

from agent.logs import get_logger
from agent.settings import app_data_dir, load_settings

log = get_logger("safety")


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


def _looks_absolute(raw: str) -> bool:
    # Windows drive path (C:\...), UNC, or posix-absolute.
    return bool(re.match(r"^[a-zA-Z]:[\\/]", raw)) or raw.startswith(("\\\\", "//", "/"))


def resolve_allowed(path: str, roots: list[str] | None = None) -> Path:
    """Resolve a tool path, tolerating the loose names a small model tends to emit.

    A full path inside an allowed root works as before. A loose name — "Downloads",
    "my documents", "root/Documents\\a.txt" — is matched to an allowed root by its
    leading folder name, so relative guesses don't resolve against the backend's cwd
    and get wrongly denied. Falls back to strict checking (which raises PathNotAllowed).
    """
    if path is None:
        raise PathNotAllowed("no path given")
    raw = str(path).strip().strip('"')
    allowed = roots if roots is not None else load_settings().allowed_roots

    if not _looks_absolute(raw):
        # Split into segments on / or \, drop noise segments, match the first real
        # segment against an allowed root's basename.
        segs = [s for s in re.split(r"[\\/]+", raw) if s not in ("", ".", "root", "~")]
        if segs:
            # Strip leading noise words *within* the first segment ("my downloads" -> "downloads").
            head_words = [w for w in segs[0].split() if w.lower() not in ("my", "the")]
            head = head_words[-1] if head_words else segs[0]
            rest = segs[1:]
            for r in allowed:
                root = Path(r)
                if root.name.casefold() == head.casefold():
                    candidate = root.joinpath(*rest) if rest else root
                    log.info("resolve_allowed: %r -> matched root %s -> %s", raw, r, candidate)
                    return resolve_and_check(str(candidate), roots)
            # No segment named a root: the model is referring to a file *inside* an
            # allowed folder by its plain name ("photo.jpg", "images\photo.jpg").
            # Resolve it against the roots, never the backend's cwd. Prefer a root
            # where the path already exists (a source), then one whose parent folder
            # exists (a destination like "images\x" after Downloads\images was made),
            # then the first root. resolve_and_check still blocks any `..` escape.
            rel = Path(*segs)
            for r in allowed:
                if (Path(r) / rel).exists():
                    log.info("resolve_allowed: %r -> found in root %s", raw, r)
                    return resolve_and_check(str(Path(r) / rel), roots)
            for r in allowed:
                if (Path(r) / rel).parent.exists():
                    log.info("resolve_allowed: %r -> parent in root %s", raw, r)
                    return resolve_and_check(str(Path(r) / rel), roots)
            if allowed:
                log.info("resolve_allowed: %r -> default first root %s", raw, allowed[0])
                return resolve_and_check(str(Path(allowed[0]) / rel), roots)
    # Absolute (or no roots configured) — strict check (raises if outside roots).
    return resolve_and_check(raw, roots)


def recycle_delete(path: Path) -> None:
    """Send a file to the Recycle Bin (recoverable), never a permanent delete."""
    send2trash(str(path))


def is_allowed_root(p: Path) -> bool:
    """Is p exactly one of the configured allowed roots (not merely inside one)?"""
    resolved = p.resolve()  # defensive: callers shouldn't have to pre-resolve a security check
    return any(str(resolved).casefold() == str(Path(r).resolve()).casefold()
               for r in load_settings().allowed_roots)


def audit(entry: dict) -> None:
    """Append one JSON line to the persistent audit log in app-data."""
    line = json.dumps(entry, ensure_ascii=False)
    with (app_data_dir() / "audit.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# The single place tool destructiveness is declared.
DESTRUCTIVE: set[str] = {"move_file", "delete_file", "batch_move"}


def needs_approval(tool_name: str, args: dict | None = None) -> bool:
    """Does this tool call require the user's approval before running?

    Name-based for always-destructive tools; write_file gates only when it
    would overwrite an existing file.
    """
    if tool_name in DESTRUCTIVE:
        return True
    return tool_name == "write_file" and bool((args or {}).get("overwrite"))


def dry_run() -> bool:
    return load_settings().dry_run
