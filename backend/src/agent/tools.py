"""In-process agent tools. Guardrails run here — the trust boundary."""
from __future__ import annotations

import shutil
from pathlib import Path

from langchain_core.tools import tool

from agent.logs import get_logger
from agent.safety import PathNotAllowed, audit, dry_run, resolve_allowed

log = get_logger("tools")

FORBIDDEN_DST_EXT = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".scr", ".lnk"}


@tool
def list_dir(path: str) -> str:
    """List the files and folders in a directory. Read-only.

    `path` may be a full path inside an allowed folder, or a loose name like
    "Downloads" / "my documents" — it is matched to an allowed folder.
    """
    log.info("list_dir(path=%r)", path)
    try:
        target = resolve_allowed(path)
    except PathNotAllowed as e:
        log.warning("list_dir DENIED: %s", e)
        audit({"tool": "list_dir", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not target.is_dir():
        log.warning("list_dir: not a directory: %s", target)
        return f"Not a directory: {target}"
    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
    log.info("list_dir OK: %s (%d entries)", target, len(entries))
    audit({"tool": "list_dir", "path": str(target), "result": "ok", "count": len(entries)})
    return "\n".join(entries) if entries else "(empty)"


@tool
def move_file(src: str, dst: str) -> str:
    """Move a file from src to dst. Destructive — requires approval.

    Both may be full paths inside an allowed folder, or loose names that are
    matched to an allowed folder.
    """
    log.info("move_file(src=%r, dst=%r)", src, dst)
    try:
        src_p = resolve_allowed(src)
        dst_p = resolve_allowed(dst)
    except PathNotAllowed as e:
        log.warning("move_file DENIED: %s", e)
        audit({"tool": "move_file", "src": src, "dst": dst, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if dst_p.suffix.lower() in FORBIDDEN_DST_EXT:
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "forbidden extension"})
        return f"Denied: cannot move to an executable/script destination ({dst_p.suffix})"
    if dst_p.exists():
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "destination exists"})
        return f"Denied: destination already exists ({dst_p})"
    if dry_run():
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "dry-run"})
        return f"[dry-run] would move {src_p.name} to {dst_p}"
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_p), str(dst_p))
    log.info("move_file OK: %s -> %s", src_p, dst_p)
    audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "ok"})
    return f"Moved {src_p.name} to {dst_p}"


TOOLS = [list_dir, move_file]
