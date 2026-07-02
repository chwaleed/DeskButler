"""In-process agent tools. Guardrails run here — the trust boundary."""
from __future__ import annotations

import shutil
import stat as stat_mod
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from agent.logs import get_logger
from agent.safety import PathNotAllowed, audit, dry_run, resolve_allowed

log = get_logger("tools")

FORBIDDEN_DST_EXT = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".scr", ".lnk"}

MAX_READ = 10_000  # chars returned to the model; more overflows a 16k context fast


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


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
    items = sorted(target.iterdir(), key=lambda p: p.name.casefold())
    dirs = sum(1 for p in items if p.is_dir())
    entries = [p.name + ("/" if p.is_dir() else "") for p in items]
    log.info("list_dir OK: %s (%d entries)", target, len(entries))
    audit({"tool": "list_dir", "path": str(target), "result": "ok", "count": len(entries)})
    if not entries:
        return "(empty)"
    # Cap the listing: a huge dump overflows the model's context and derails it.
    MAX = 120
    shown = entries[:MAX]
    header = f"{len(entries)} entries — {len(entries) - dirs} files, {dirs} folders"
    tail = [f"…{len(entries) - MAX} more entries"] if len(entries) > MAX else []
    return "\n".join([header, *shown, *tail])


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


@tool
def read_file(path: str) -> str:
    """Read a text file's content. Read-only. Binary files are refused; long files are truncated.

    `path` may be a full path inside an allowed folder, or a loose name that is
    matched to an allowed folder.
    """
    log.info("read_file(path=%r)", path)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        log.warning("read_file DENIED: %s", e)
        audit({"tool": "read_file", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not p.is_file():
        audit({"tool": "read_file", "path": str(p), "result": "not-a-file"})
        return f"Not a file: {p}"
    with p.open("rb") as fh:
        raw = fh.read(4 * MAX_READ)
    if b"\x00" in raw[:8192]:
        audit({"tool": "read_file", "path": str(p), "result": "refused-binary"})
        return f"Refused: {p.name} looks like a binary file"
    text = raw.decode("utf-8", errors="replace")
    total = p.stat().st_size
    audit({"tool": "read_file", "path": str(p), "result": "ok", "bytes": total})
    if len(text) > MAX_READ or total > len(raw):
        return text[:MAX_READ] + f"\n…truncated ({_fmt_size(total)} total)"
    return text


@tool
def file_info(path: str) -> str:
    """Show a file or folder's size, type, and created/modified dates. Read-only."""
    log.info("file_info(path=%r)", path)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        audit({"tool": "file_info", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not p.exists():
        audit({"tool": "file_info", "path": str(p), "result": "not-found"})
        return f"Not found: {p}"
    st = p.stat()
    kind = "folder" if p.is_dir() else f"file ({p.suffix.lower() or 'no extension'})"
    size = "-" if p.is_dir() else _fmt_size(st.st_size)
    fmt = "%Y-%m-%d %H:%M"
    lines = [
        str(p),
        f"type: {kind}",
        f"size: {size}",
        f"created: {datetime.fromtimestamp(st.st_ctime).strftime(fmt)}",
        f"modified: {datetime.fromtimestamp(st.st_mtime).strftime(fmt)}",
    ]
    attrs = getattr(st, "st_file_attributes", 0)
    if hasattr(stat_mod, "FILE_ATTRIBUTE_HIDDEN") and attrs & stat_mod.FILE_ATTRIBUTE_HIDDEN:
        lines.append("hidden: yes")
    audit({"tool": "file_info", "path": str(p), "result": "ok"})
    return "\n".join(lines)


@tool
def create_folder(path: str) -> str:
    """Create a folder, including missing parent folders. Does nothing if it already exists."""
    log.info("create_folder(path=%r)", path)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        audit({"tool": "create_folder", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if p.exists():
        audit({"tool": "create_folder", "path": str(p), "result": "already-exists"})
        return f"Already exists: {p}"
    if dry_run():
        audit({"tool": "create_folder", "path": str(p), "result": "dry-run"})
        return f"[dry-run] would create folder {p}"
    p.mkdir(parents=True, exist_ok=True)
    log.info("create_folder OK: %s", p)
    audit({"tool": "create_folder", "path": str(p), "result": "ok"})
    return f"Created folder {p}"


@tool
def copy_file(src: str, dst: str) -> str:
    """Copy a file or folder from src to dst. Fails if the destination already exists."""
    log.info("copy_file(src=%r, dst=%r)", src, dst)
    try:
        src_p = resolve_allowed(src)
        dst_p = resolve_allowed(dst)
    except PathNotAllowed as e:
        log.warning("copy_file DENIED: %s", e)
        audit({"tool": "copy_file", "src": src, "dst": dst, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if dst_p.suffix.lower() in FORBIDDEN_DST_EXT:
        audit({"tool": "copy_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "forbidden extension"})
        return f"Denied: cannot copy to an executable/script destination ({dst_p.suffix})"
    if not src_p.exists():
        audit({"tool": "copy_file", "src": str(src_p), "dst": str(dst_p), "result": "not-found"})
        return f"Not found: {src_p}"
    if dst_p.exists():
        audit({"tool": "copy_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "destination exists"})
        return f"Denied: destination already exists ({dst_p})"
    if dry_run():
        audit({"tool": "copy_file", "src": str(src_p), "dst": str(dst_p), "result": "dry-run"})
        return f"[dry-run] would copy {src_p.name} to {dst_p}"
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if src_p.is_dir():
        shutil.copytree(str(src_p), str(dst_p))
    else:
        shutil.copy2(str(src_p), str(dst_p))
    log.info("copy_file OK: %s -> %s", src_p, dst_p)
    audit({"tool": "copy_file", "src": str(src_p), "dst": str(dst_p), "result": "ok"})
    return f"Copied {src_p.name} to {dst_p}"


TOOLS = [list_dir, move_file, read_file, file_info, create_folder, copy_file]
