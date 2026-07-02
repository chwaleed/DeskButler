"""In-process agent tools. Guardrails run here — the trust boundary."""
from __future__ import annotations

import json
import shutil
import stat as stat_mod
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from agent.logs import get_logger
from agent.safety import (
    PathNotAllowed,
    audit,
    dry_run,
    is_allowed_root,
    recycle_delete,
    resolve_allowed,
)

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


@tool
def write_file(path: str, content: str, overwrite: bool = False) -> str:
    """Create a text file with the given content.

    Fails if the file already exists unless overwrite=true (overwriting
    requires the user's approval).
    """
    log.info("write_file(path=%r, %d chars, overwrite=%s)", path, len(content or ""), overwrite)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        log.warning("write_file DENIED: %s", e)
        audit({"tool": "write_file", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if p.suffix.lower() in FORBIDDEN_DST_EXT:
        audit({"tool": "write_file", "path": str(p), "result": "denied", "error": "forbidden extension"})
        return f"Denied: refusing to write executable/script files ({p.suffix})"
    if p.exists() and not overwrite:
        audit({"tool": "write_file", "path": str(p), "result": "denied", "error": "exists"})
        return f"Denied: file already exists ({p}). Pass overwrite=true to replace it."
    if dry_run():
        audit({"tool": "write_file", "path": str(p), "result": "dry-run"})
        return f"[dry-run] would write {len(content)} characters to {p}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    log.info("write_file OK: %s (%d chars)", p, len(content))
    audit({"tool": "write_file", "path": str(p), "result": "ok", "chars": len(content), "overwrite": overwrite})
    return f"Wrote {len(content)} characters to {p}"


@tool
def delete_file(path: str) -> str:
    """Delete a file or folder. It goes to the Recycle Bin (recoverable), never permanently erased. Destructive — requires approval."""
    log.info("delete_file(path=%r)", path)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        log.warning("delete_file DENIED: %s", e)
        audit({"tool": "delete_file", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not p.exists():
        audit({"tool": "delete_file", "path": str(p), "result": "not-found"})
        return f"Not found: {p}"
    if is_allowed_root(p):
        audit({"tool": "delete_file", "path": str(p), "result": "denied", "error": "is allowed root"})
        return f"Denied: refusing to delete an allowed folder itself ({p})"
    if dry_run():
        audit({"tool": "delete_file", "path": str(p), "result": "dry-run"})
        return f"[dry-run] would send {p.name} to the Recycle Bin"
    recycle_delete(p)
    log.info("delete_file OK: %s", p)
    audit({"tool": "delete_file", "path": str(p), "result": "ok"})
    return f"Sent {p.name} to the Recycle Bin (recoverable)"


@tool
def folder_stats(path: str) -> str:
    """Summarize a folder: file count and total size grouped by extension, recursive. Read-only.

    Use this to get an overview before organizing a folder.
    """
    log.info("folder_stats(path=%r)", path)
    try:
        p = resolve_allowed(path)
    except PathNotAllowed as e:
        audit({"tool": "folder_stats", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not p.is_dir():
        return f"Not a directory: {p}"
    by_ext: dict[str, list[int]] = {}
    count = total = 0
    MAX_FILES = 50_000  # ponytail: hard stop so a mistaken root doesn't walk a whole drive
    for f in p.rglob("*"):
        if not f.is_file():
            continue
        try:
            sz = f.stat().st_size
        except OSError:
            sz = 0
        e = by_ext.setdefault(f.suffix.lower() or "(none)", [0, 0])
        e[0] += 1
        e[1] += sz
        count += 1
        total += sz
        if count >= MAX_FILES:
            break
    audit({"tool": "folder_stats", "path": str(p), "result": "ok", "files": count})
    if count == 0:
        return f"{p} is empty (no files)"
    rows = sorted(by_ext.items(), key=lambda kv: kv[1][1], reverse=True)
    lines = [f"{count} files, {_fmt_size(total)} total (recursive)"]
    lines += [f"{ext}: {n} files, {_fmt_size(sz)}" for ext, (n, sz) in rows[:20]]
    if len(rows) > 20:
        lines.append(f"…{len(rows) - 20} more extensions")
    return "\n".join(lines)


@tool
def batch_move(moves: list[dict] | str) -> str:
    """Move MANY files in one call — use this instead of repeated move_file calls when organizing.

    `moves` is a list of {"src": ..., "dst": ...} objects. One approval covers
    the whole batch. Items that fail (missing source, destination exists,
    outside allowed folders) are skipped and reported; the rest still move.
    """
    if isinstance(moves, str):
        # ponytail: small models sometimes stringify the list — tolerate it.
        try:
            moves = json.loads(moves)
        except json.JSONDecodeError:
            return "Denied: moves must be a list of {src, dst} objects"
    if not isinstance(moves, list) or not moves:
        return "Denied: moves must be a non-empty list of {src, dst} objects"
    MAX_BATCH = 200
    if len(moves) > MAX_BATCH:
        return f"Denied: too many moves in one batch ({len(moves)} > {MAX_BATCH})"
    log.info("batch_move(%d moves)", len(moves))
    dr = dry_run()
    done: list[str] = []
    skipped: list[str] = []
    for m in moves:
        src, dst = (m or {}).get("src"), (m or {}).get("dst")
        try:
            src_p = resolve_allowed(src)
            dst_p = resolve_allowed(dst)
        except PathNotAllowed as e:
            skipped.append(f"{src}: denied ({e})")
            continue
        if dst_p.suffix.lower() in FORBIDDEN_DST_EXT:
            skipped.append(f"{src_p.name}: forbidden destination extension")
            continue
        if not src_p.exists():
            skipped.append(f"{src_p.name}: source not found")
            continue
        if dst_p.exists():
            skipped.append(f"{src_p.name}: destination already exists")
            continue
        if dr:
            done.append(f"[dry-run] {src_p.name} -> {dst_p}")
            continue
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        done.append(f"{src_p.name} -> {dst_p}")
    log.info("batch_move OK: %d moved, %d skipped", len(done), len(skipped))
    audit({"tool": "batch_move", "result": "dry-run" if dr else "ok",
           "moved": len(done), "skipped": len(skipped)})
    header = f"Moved {len(done)} of {len(moves)}." + (" (dry-run: nothing was changed)" if dr else "")
    SHOW = 50  # cap the report, same reason list_dir caps
    lines = [header, *done[:SHOW]]
    if len(done) > SHOW:
        lines.append(f"…{len(done) - SHOW} more")
    if skipped:
        lines.append(f"Skipped {len(skipped)}:")
        lines += skipped[:SHOW]
        if len(skipped) > SHOW:
            lines.append(f"…{len(skipped) - SHOW} more")
    return "\n".join(lines)


TOOLS = [
    list_dir, move_file, read_file, file_info, create_folder,
    copy_file, write_file, delete_file, folder_stats, batch_move,
]
