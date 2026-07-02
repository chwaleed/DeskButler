# Core File Tools + Batch Organize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement build-order step 1 of `docs/tools.md` — Phase 1 core file tools (`copy_file`, `delete_file`, `create_folder`, `write_file`, `read_file`, `file_info`) plus the organize core (`folder_stats`, `batch_move`) — bringing DeskButler from 2 tools to 10 and delivering the "organize my Downloads" demo.

**Architecture:** Every tool is an in-process LangChain `@tool` function in `backend/src/agent/tools.py`, following the exact pattern `list_dir`/`move_file` already use: `resolve_allowed()` at the top (trust boundary), `audit()` on every outcome, `dry_run()` honored by every mutating tool, capped text output. The safety gate in `graph.py` switches from a name-only `is_destructive()` check to an args-aware `needs_approval(name, args)` predicate (needed because `write_file` is destructive only when `overwrite=true`). `batch_move` executes a whole organize plan behind ONE approval; the frontend `ApprovalCard` learns to render its list of moves.

**Tech Stack:** Python 3.11 (uv-managed), LangChain `@tool` / LangGraph, pytest, send2trash (already a dep — no new dependencies), React + TypeScript frontend (vite single-file build).

## Global Constraints

- **C: drive is FULL.** Every backend command MUST be prefixed with: `export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache"`. Every npm command MUST be prefixed with: `export npm_config_cache="d:/Local Desktop/.npm-cache"`. Run everything from Git Bash.
- **Backend test command:** `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest <args>`
- **Commits:** authored as the repo's configured user (Ch Waleed). NO `Co-Authored-By` trailers, no Claude attribution — this is a hard user requirement.
- **No new Python dependencies.** Everything here uses stdlib + already-installed packages (`send2trash` is already in `pyproject.toml`).
- **Tool output is always capped** — no tool may return unbounded text (existing cap style: `list_dir`'s `MAX = 120` with `…N more` tail).
- **Every mutating tool honors `dry_run()`** and returns a `[dry-run]`-prefixed message without touching disk.
- **Every tool logs via `log = get_logger("tools")` and writes an `audit({...})` line** for ok/denied outcomes, matching the existing pattern in `tools.py`.
- Known harmless test artifact: pytest teardown may print a `PermissionError` about a temp `checkpoints.db` — ignore it (the loop thread holds the DB; pre-existing).

---

### Task 1: Args-aware approval predicate (`needs_approval`)

The gate currently keys on tool *name* only (`is_destructive`). `write_file` breaks that model — destructive only when `overwrite=true`. Replace the predicate before adding any tools, so every later task just adds a name to `DESTRUCTIVE`.

**Files:**
- Modify: `backend/src/agent/safety.py:98-103` (replace `DESTRUCTIVE` comment block + `is_destructive`)
- Modify: `backend/src/agent/graph.py:12` (import) and `backend/src/agent/graph.py:54` (gate condition)
- Test: `backend/tests/test_safety.py`

**Interfaces:**
- Consumes: existing `DESTRUCTIVE: set[str]` in `safety.py`.
- Produces: `needs_approval(tool_name: str, args: dict | None = None) -> bool` in `agent.safety` — later tasks add `"delete_file"` and `"batch_move"` to `DESTRUCTIVE` (done here, ahead of the tools) and rely on the `write_file`+`overwrite` special case. `is_destructive` is deleted (only `graph.py` used it).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_safety.py`:

```python
def test_needs_approval_matrix():
    from agent.safety import needs_approval
    # Name-based destructive tools always gate.
    assert needs_approval("move_file", {})
    assert needs_approval("delete_file", {})
    assert needs_approval("batch_move", {"moves": [{"src": "a", "dst": "b"}]})
    # Read-only / creating tools don't.
    assert not needs_approval("list_dir", {})
    assert not needs_approval("copy_file", {})
    # write_file gates ONLY when overwriting.
    assert not needs_approval("write_file", {"path": "a.txt", "content": "x"})
    assert not needs_approval("write_file", {"overwrite": False})
    assert needs_approval("write_file", {"overwrite": True})
    # Missing args tolerated.
    assert not needs_approval("write_file", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_safety.py::test_needs_approval_matrix -v`
Expected: FAIL with `ImportError: cannot import name 'needs_approval'`

- [ ] **Step 3: Implement**

In `backend/src/agent/safety.py`, replace lines 98–103 (the `DESTRUCTIVE` declaration and `is_destructive`) with:

```python
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
```

In `backend/src/agent/graph.py`, change line 12 from:

```python
from agent.safety import dry_run, is_destructive
```

to:

```python
from agent.safety import dry_run, needs_approval
```

and change the gate condition (line 54) from:

```python
            if is_destructive(call["name"]) and not dry_run():
```

to:

```python
            if needs_approval(call["name"], call["args"] or {}) and not dry_run():
```

- [ ] **Step 4: Verify nothing else referenced `is_destructive`**

Run: `cd "/d/Local Desktop" && grep -rn "is_destructive" backend/`
Expected: no matches.

- [ ] **Step 5: Run the full backend suite**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest -v`
Expected: all tests PASS (previously 17, now 18).

- [ ] **Step 6: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/safety.py backend/src/agent/graph.py backend/tests/test_safety.py && git commit -m "feat: args-aware needs_approval predicate replaces is_destructive"
```

---

### Task 2: Test fixture + read-only tools (`read_file`, `file_info`)

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_tools.py`
- Modify: `backend/src/agent/tools.py` (add helpers + 2 tools, extend `TOOLS`)

**Interfaces:**
- Consumes: `resolve_allowed`, `PathNotAllowed`, `audit` from `agent.safety` (already imported in `tools.py`).
- Produces: `sandbox` pytest fixture returning `(root: Path, settings)` — every later task's tests use it. `_fmt_size(n: int) -> str` module-level helper in `tools.py` — Task 6 (`folder_stats`) reuses it. Tools `read_file(path: str) -> str`, `file_info(path: str) -> str` registered in `TOOLS`.

- [ ] **Step 1: Create the shared fixture**

Create `backend/tests/conftest.py`:

```python
import pytest


class FakeSettings:
    def __init__(self, roots):
        self.allowed_roots = roots
        self.model = "test"
        self.dry_run = False


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A temp allowed root with settings + audit patched so tools run isolated.

    Returns (root, settings). Flip settings.dry_run = True inside a test to
    exercise dry-run behavior.
    """
    root = tmp_path / "Downloads"
    root.mkdir()
    settings = FakeSettings([str(root)])
    monkeypatch.setattr("agent.safety.load_settings", lambda: settings)
    monkeypatch.setattr("agent.safety.app_data_dir", lambda: tmp_path)
    return root, settings
```

(No production code depends on this — it's test infrastructure. `agent.tools.dry_run` is the function imported from `agent.safety`, which reads `load_settings()` at call time, so patching `agent.safety.load_settings` covers dry-run toggling too.)

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_tools.py`:

```python
"""Tests for the file tools. All run against the `sandbox` fixture (conftest.py)."""
from agent import tools


# ---- read_file ----

def test_read_file_returns_content(sandbox):
    root, _ = sandbox
    f = root / "note.txt"
    f.write_text("hello world", encoding="utf-8")
    assert tools.read_file.invoke({"path": str(f)}) == "hello world"


def test_read_file_caps_output(sandbox):
    root, _ = sandbox
    f = root / "big.txt"
    f.write_text("x" * 50_000, encoding="utf-8")
    out = tools.read_file.invoke({"path": str(f)})
    assert len(out) < 12_000
    assert "truncated" in out


def test_read_file_refuses_binary(sandbox):
    root, _ = sandbox
    f = root / "app.bin"
    f.write_bytes(b"MZ\x00\x01\x02binary")
    out = tools.read_file.invoke({"path": str(f)})
    assert "Refused" in out


def test_read_file_denies_outside_roots(sandbox):
    out = tools.read_file.invoke({"path": r"C:\Windows\win.ini"})
    assert out.startswith("Denied:")


# ---- file_info ----

def test_file_info_reports_size_and_type(sandbox):
    root, _ = sandbox
    f = root / "doc.pdf"
    f.write_bytes(b"x" * 2048)
    out = tools.file_info.invoke({"path": str(f)})
    assert "2.0 KB" in out
    assert ".pdf" in out
    assert "modified:" in out


def test_file_info_on_folder(sandbox):
    root, _ = sandbox
    out = tools.file_info.invoke({"path": str(root)})
    assert "folder" in out
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v`
Expected: FAIL with `AttributeError: module 'agent.tools' has no attribute 'read_file'`

- [ ] **Step 4: Implement**

In `backend/src/agent/tools.py`, add to the imports block (after `import shutil`):

```python
import stat as stat_mod
from datetime import datetime
```

Add after the `FORBIDDEN_DST_EXT` line:

```python
MAX_READ = 10_000  # chars returned to the model; more overflows a 16k context fast


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
```

Add the two tools (before the `TOOLS` list):

```python
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
```

Update the registry at the bottom:

```python
TOOLS = [list_dir, move_file, read_file, file_info]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v`
Expected: 6 PASS. Then run the full suite (`uv run pytest`) — everything passes.

- [ ] **Step 6: Commit**

```bash
cd "/d/Local Desktop" && git add backend/tests/conftest.py backend/tests/test_tools.py backend/src/agent/tools.py && git commit -m "feat: read_file and file_info tools"
```

---

### Task 3: `create_folder` + `copy_file`

**Files:**
- Modify: `backend/src/agent/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `sandbox` fixture (Task 2), `resolve_allowed`, `dry_run`, `audit`, `FORBIDDEN_DST_EXT`.
- Produces: `create_folder(path: str) -> str`, `copy_file(src: str, dst: str) -> str` in `TOOLS`. Neither is in `DESTRUCTIVE` (copy fails if destination exists → nothing is ever lost).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tools.py`:

```python
# ---- create_folder ----

def test_create_folder_creates_with_parents(sandbox):
    root, _ = sandbox
    target = root / "sorted" / "images"
    out = tools.create_folder.invoke({"path": str(target)})
    assert target.is_dir()
    assert "Created" in out


def test_create_folder_noop_if_exists(sandbox):
    root, _ = sandbox
    out = tools.create_folder.invoke({"path": str(root)})
    assert "Already exists" in out


def test_create_folder_dry_run(sandbox):
    root, settings = sandbox
    settings.dry_run = True
    target = root / "newdir"
    out = tools.create_folder.invoke({"path": str(target)})
    assert "[dry-run]" in out
    assert not target.exists()


# ---- copy_file ----

def test_copy_file_copies(sandbox):
    root, _ = sandbox
    src = root / "a.txt"
    src.write_text("data")
    dst = root / "backup" / "a.txt"
    out = tools.copy_file.invoke({"src": str(src), "dst": str(dst)})
    assert dst.read_text() == "data"
    assert src.exists()  # copy, not move
    assert "Copied" in out


def test_copy_file_refuses_existing_destination(sandbox):
    root, _ = sandbox
    src = root / "a.txt"
    src.write_text("new")
    dst = root / "b.txt"
    dst.write_text("old")
    out = tools.copy_file.invoke({"src": str(src), "dst": str(dst)})
    assert "Denied" in out
    assert dst.read_text() == "old"


def test_copy_file_copies_folder(sandbox):
    root, _ = sandbox
    (root / "proj").mkdir()
    (root / "proj" / "f.txt").write_text("x")
    out = tools.copy_file.invoke({"src": str(root / "proj"), "dst": str(root / "proj2")})
    assert (root / "proj2" / "f.txt").read_text() == "x"
    assert "Copied" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v -k "create_folder or copy_file"`
Expected: FAIL with `AttributeError: module 'agent.tools' has no attribute 'create_folder'`

- [ ] **Step 3: Implement**

Add to `backend/src/agent/tools.py` (before `TOOLS`):

```python
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
```

Update the registry:

```python
TOOLS = [list_dir, move_file, read_file, file_info, create_folder, copy_file]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/tools.py backend/tests/test_tools.py && git commit -m "feat: create_folder and copy_file tools"
```

---

### Task 4: `write_file`

**Files:**
- Modify: `backend/src/agent/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `needs_approval` special case from Task 1 (gates `write_file` only when `overwrite=true` — the tool itself never asks; the gate does).
- Produces: `write_file(path: str, content: str, overwrite: bool = False) -> str` in `TOOLS`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tools.py`:

```python
# ---- write_file ----

def test_write_file_creates_text_file(sandbox):
    root, _ = sandbox
    target = root / "notes" / "todo.md"
    out = tools.write_file.invoke({"path": str(target), "content": "# Todo\n- buy milk"})
    assert target.read_text(encoding="utf-8") == "# Todo\n- buy milk"
    assert "Wrote" in out


def test_write_file_refuses_overwrite_without_flag(sandbox):
    root, _ = sandbox
    f = root / "keep.txt"
    f.write_text("original")
    out = tools.write_file.invoke({"path": str(f), "content": "clobbered"})
    assert "Denied" in out
    assert f.read_text() == "original"


def test_write_file_overwrites_with_flag(sandbox):
    root, _ = sandbox
    f = root / "keep.txt"
    f.write_text("original")
    out = tools.write_file.invoke({"path": str(f), "content": "new", "overwrite": True})
    assert f.read_text(encoding="utf-8") == "new"
    assert "Wrote" in out


def test_write_file_refuses_executable_extension(sandbox):
    root, _ = sandbox
    out = tools.write_file.invoke({"path": str(root / "evil.bat"), "content": "del /q *"})
    assert "Denied" in out
    assert not (root / "evil.bat").exists()


def test_write_file_dry_run(sandbox):
    root, settings = sandbox
    settings.dry_run = True
    target = root / "new.txt"
    out = tools.write_file.invoke({"path": str(target), "content": "x"})
    assert "[dry-run]" in out
    assert not target.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v -k write_file`
Expected: FAIL with `AttributeError: module 'agent.tools' has no attribute 'write_file'`

- [ ] **Step 3: Implement**

Add to `backend/src/agent/tools.py` (before `TOOLS`):

```python
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
```

Update the registry:

```python
TOOLS = [list_dir, move_file, read_file, file_info, create_folder, copy_file, write_file]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/tools.py backend/tests/test_tools.py && git commit -m "feat: write_file tool with overwrite gating"
```

---

### Task 5: `delete_file` (Recycle Bin only)

**Files:**
- Modify: `backend/src/agent/safety.py` (add `is_allowed_root` helper)
- Modify: `backend/src/agent/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `recycle_delete(path: Path) -> None` (exists in `safety.py:86`), `DESTRUCTIVE` already contains `"delete_file"` (Task 1).
- Produces: `is_allowed_root(p: Path) -> bool` in `agent.safety` (lives there because it reads `load_settings`, which tests patch at `agent.safety.load_settings`); `delete_file(path: str) -> str` in `TOOLS`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tools.py`:

```python
# ---- delete_file ----

def test_delete_file_sends_to_recycle_bin(sandbox, monkeypatch):
    root, _ = sandbox
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    f = root / "old.txt"
    f.write_text("x")
    out = tools.delete_file.invoke({"path": str(f)})
    assert trashed == [str(f.resolve())]
    assert "Recycle Bin" in out


def test_delete_file_refuses_allowed_root_itself(sandbox, monkeypatch):
    root, _ = sandbox
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    out = tools.delete_file.invoke({"path": str(root)})
    assert "Denied" in out
    assert trashed == []


def test_delete_file_dry_run(sandbox, monkeypatch):
    root, settings = sandbox
    settings.dry_run = True
    trashed = []
    monkeypatch.setattr("agent.tools.recycle_delete", lambda p: trashed.append(str(p)))
    f = root / "old.txt"
    f.write_text("x")
    out = tools.delete_file.invoke({"path": str(f)})
    assert "[dry-run]" in out
    assert trashed == [] and f.exists()


def test_delete_file_missing_path(sandbox):
    root, _ = sandbox
    out = tools.delete_file.invoke({"path": str(root / "ghost.txt")})
    assert "Not found" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v -k delete_file`
Expected: FAIL with `AttributeError: module 'agent.tools' has no attribute 'delete_file'`

- [ ] **Step 3: Implement**

In `backend/src/agent/safety.py`, add after `recycle_delete`:

```python
def is_allowed_root(p: Path) -> bool:
    """Is p exactly one of the configured allowed roots (not merely inside one)?"""
    return any(str(p).casefold() == str(Path(r).resolve()).casefold()
               for r in load_settings().allowed_roots)
```

In `backend/src/agent/tools.py`, extend the safety import (line 10) to:

```python
from agent.safety import (
    PathNotAllowed,
    audit,
    dry_run,
    is_allowed_root,
    recycle_delete,
    resolve_allowed,
)
```

Add the tool (before `TOOLS`):

```python
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
```

Update the registry:

```python
TOOLS = [list_dir, move_file, read_file, file_info, create_folder, copy_file, write_file, delete_file]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest -v`
Expected: full suite PASS (delete_file gating is already covered by `test_needs_approval_matrix` from Task 1).

- [ ] **Step 5: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/safety.py backend/src/agent/tools.py backend/tests/test_tools.py && git commit -m "feat: delete_file tool (recycle bin, root-guarded)"
```

---

### Task 6: `folder_stats`

**Files:**
- Modify: `backend/src/agent/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `_fmt_size` helper (Task 2).
- Produces: `folder_stats(path: str) -> str` in `TOOLS` — the overview the model reads before building a `batch_move` plan.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tools.py`:

```python
# ---- folder_stats ----

def test_folder_stats_groups_by_extension(sandbox):
    root, _ = sandbox
    (root / "a.jpg").write_bytes(b"x" * 1000)
    (root / "b.jpg").write_bytes(b"x" * 1000)
    (root / "c.pdf").write_bytes(b"x" * 5000)
    (root / "sub").mkdir()
    (root / "sub" / "d.jpg").write_bytes(b"x" * 1000)  # recursive
    out = tools.folder_stats.invoke({"path": str(root)})
    assert "4 files" in out
    assert ".jpg: 3 files" in out
    assert ".pdf: 1 files" in out


def test_folder_stats_handles_no_extension(sandbox):
    root, _ = sandbox
    (root / "README").write_bytes(b"x")
    out = tools.folder_stats.invoke({"path": str(root)})
    assert "(none): 1 files" in out


def test_folder_stats_denies_outside_roots(sandbox):
    out = tools.folder_stats.invoke({"path": r"C:\Windows"})
    assert out.startswith("Denied:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v -k folder_stats`
Expected: FAIL with `AttributeError: module 'agent.tools' has no attribute 'folder_stats'`

- [ ] **Step 3: Implement**

Add to `backend/src/agent/tools.py` (before `TOOLS`):

```python
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
```

Update the registry:

```python
TOOLS = [list_dir, move_file, read_file, file_info, create_folder, copy_file, write_file, delete_file, folder_stats]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/tools.py backend/tests/test_tools.py && git commit -m "feat: folder_stats tool"
```

---

### Task 7: `batch_move` — the organize workhorse

One tool call executes a whole organize plan; ONE approval covers the batch. Per-item failures skip-and-report instead of aborting.

**Files:**
- Modify: `backend/src/agent/tools.py` (add `import json` + tool)
- Test: `backend/tests/test_tools.py` and `backend/tests/test_gate.py`

**Interfaces:**
- Consumes: `DESTRUCTIVE` already contains `"batch_move"` (Task 1), so the existing gate pauses on it with payload `{"tool": "batch_move", "args": {"moves": [...]}, "message": "Approve batch_move?"}` — Task 9's frontend work renders that `moves` array.
- Produces: `batch_move(moves: list[dict]) -> str` in `TOOLS`. Each item is `{"src": str, "dst": str}`. Tolerates a JSON-string `moves` (small models sometimes stringify).

- [ ] **Step 1: Write the failing tool tests**

Append to `backend/tests/test_tools.py`:

```python
# ---- batch_move ----

def test_batch_move_moves_all(sandbox):
    root, _ = sandbox
    (root / "a.jpg").write_text("a")
    (root / "b.jpg").write_text("b")
    moves = [
        {"src": str(root / "a.jpg"), "dst": str(root / "Pictures" / "a.jpg")},
        {"src": str(root / "b.jpg"), "dst": str(root / "Pictures" / "b.jpg")},
    ]
    out = tools.batch_move.invoke({"moves": moves})
    assert (root / "Pictures" / "a.jpg").exists()
    assert (root / "Pictures" / "b.jpg").exists()
    assert "Moved 2 of 2" in out


def test_batch_move_skips_and_reports_failures(sandbox):
    root, _ = sandbox
    (root / "ok.txt").write_text("x")
    (root / "taken.txt").write_text("x")
    (root / "dest.txt").write_text("already here")
    moves = [
        {"src": str(root / "ok.txt"), "dst": str(root / "sorted" / "ok.txt")},
        {"src": str(root / "ghost.txt"), "dst": str(root / "sorted" / "ghost.txt")},
        {"src": str(root / "taken.txt"), "dst": str(root / "dest.txt")},
        {"src": r"C:\Windows\win.ini", "dst": str(root / "win.ini")},
    ]
    out = tools.batch_move.invoke({"moves": moves})
    assert (root / "sorted" / "ok.txt").exists()
    assert (root / "taken.txt").exists()  # skipped, still in place
    assert "Moved 1 of 4" in out
    assert "Skipped 3" in out


def test_batch_move_dry_run_touches_nothing(sandbox):
    root, settings = sandbox
    settings.dry_run = True
    (root / "a.txt").write_text("x")
    out = tools.batch_move.invoke(
        {"moves": [{"src": str(root / "a.txt"), "dst": str(root / "s" / "a.txt")}]}
    )
    assert "[dry-run]" in out
    assert (root / "a.txt").exists() and not (root / "s").exists()


def test_batch_move_tolerates_json_string(sandbox):
    import json
    root, _ = sandbox
    (root / "a.txt").write_text("x")
    moves = json.dumps([{"src": str(root / "a.txt"), "dst": str(root / "s" / "a.txt")}])
    out = tools.batch_move.invoke({"moves": moves})
    assert (root / "s" / "a.txt").exists()
    assert "Moved 1 of 1" in out


def test_batch_move_rejects_empty_and_oversized(sandbox):
    root, _ = sandbox
    assert "Denied" in tools.batch_move.invoke({"moves": []})
    too_many = [{"src": f"a{i}", "dst": f"b{i}"} for i in range(201)]
    assert "Denied" in tools.batch_move.invoke({"moves": too_many})
```

- [ ] **Step 2: Write the failing gate test**

Append to `backend/tests/test_gate.py`:

```python
def _model_that_batch_moves_then_answers():
    call = AIMessage(
        content="",
        tool_calls=[{
            "name": "batch_move",
            "args": {"moves": [{"src": "a.txt", "dst": "s/a.txt"}]},
            "id": "call1",
        }],
    )
    return FakeToolModel(messages=iter([call, AIMessage(content="Done.")]))


def test_batch_move_pauses_for_approval(monkeypatch):
    monkeypatch.setattr("agent.graph.dry_run", lambda: False)
    graph = build_graph(model=_model_that_batch_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t4"}}
    graph.invoke({"messages": [HumanMessage("organize my downloads")]}, config)
    state = graph.get_state(config)
    assert state.next
    assert state.tasks and any(t.interrupts for t in state.tasks)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_tools.py tests/test_gate.py -v -k batch_move`
Expected: FAIL — tools tests with `AttributeError`, gate test with a graph error because `batch_move` isn't a registered tool.

- [ ] **Step 4: Implement**

In `backend/src/agent/tools.py`, add `import json` to the imports (after `from __future__ import annotations`):

```python
import json
```

Add the tool (before `TOOLS`):

```python
@tool
def batch_move(moves: list[dict]) -> str:
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
```

Update the registry (final form — 10 tools):

```python
TOOLS = [
    list_dir, move_file, read_file, file_info, create_folder,
    copy_file, write_file, delete_file, folder_stats, batch_move,
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest -v`
Expected: full suite PASS.

- [ ] **Step 6: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/tools.py backend/tests/test_tools.py backend/tests/test_gate.py && git commit -m "feat: batch_move tool - one approval for a whole organize plan"
```

---

### Task 8: System prompt for 10 tools

The prompt must teach the two behaviors the tools can't enforce: use `batch_move` (not repeated `move_file`) for bulk jobs, and `move_file` doubles as rename.

**Files:**
- Modify: `backend/src/agent/prompts.py`
- Test: `backend/tests/test_safety.py` (cheapest home — no new file for two asserts)

**Interfaces:**
- Consumes: nothing new.
- Produces: same signature `system_prompt(allowed_roots: list[str]) -> str`; only the text changes.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_safety.py`:

```python
def test_system_prompt_teaches_batch_and_rename():
    from agent.prompts import system_prompt
    p = system_prompt([r"C:\Users\x\Downloads"])
    assert r"C:\Users\x\Downloads" in p
    assert "batch_move" in p
    assert "rename" in p.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest tests/test_safety.py::test_system_prompt_teaches_batch_and_rename -v`
Expected: FAIL on `assert "batch_move" in p`

- [ ] **Step 3: Implement**

Replace the body of `system_prompt` in `backend/src/agent/prompts.py` with:

```python
def system_prompt(allowed_roots: list[str]) -> str:
    roots = "\n".join(f"  - {r}" for r in allowed_roots) or "  (none configured)"
    return (
        "You are DeskButler, a local file assistant on the user's Windows computer. "
        "Using the provided tools you can list, read, and inspect files, create "
        "folders and text files, copy, move, and delete files, and summarize "
        "folder contents.\n\n"
        "You may ONLY operate inside these allowed folders (use these exact paths):\n"
        f"{roots}\n\n"
        "Rules:\n"
        "- When the user names a folder loosely (e.g. \"my downloads\"), map it to "
        "the matching allowed path above. Never guess at other locations.\n"
        "- To rename a file, use move_file with the new name in dst.\n"
        "- To move or organize MANY files, first look at the folder (list_dir or "
        "folder_stats), then call batch_move ONCE with the complete list of "
        "{src, dst} moves. Never call move_file repeatedly for a bulk job.\n"
        "- If a tool returns 'Denied', do NOT retry with a different guessed path — "
        "tell the user what happened and stop.\n"
        "When you have finished the request, reply with a short plain-language summary."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest -v`
Expected: full suite PASS.

- [ ] **Step 5: Commit**

```bash
cd "/d/Local Desktop" && git add backend/src/agent/prompts.py backend/tests/test_safety.py && git commit -m "feat: system prompt covers the 10-tool set and batch_move rule"
```

---

### Task 9: Frontend — approval card renders a batch plan

`ApprovalCard` currently prints every arg with `String(v)`; a `moves` array would render as `[object Object],[object Object]`. Render arrays as a scrollable list of `src → dst` lines (the blast-radius view). Also refresh the empty-state suggestions to advertise organizing.

**Files:**
- Modify: `frontend/src/components/ApprovalCard.tsx`
- Modify: `frontend/src/components/ChatThread.tsx:6-10` (SUGGESTIONS)

**Interfaces:**
- Consumes: gate payload `{tool, args, message}` where `args.moves` is `Array<{src: string, dst: string}>` (Task 7). No bridge/type changes — `args` is already `Record<string, unknown>`.
- Produces: nothing consumed later; UI only.

(No frontend test runner exists in this project — verification is the type-checked build plus the manual e2e in Task 10.)

- [ ] **Step 1: Implement ApprovalCard rendering**

Replace the full contents of `frontend/src/components/ApprovalCard.tsx` with:

```tsx
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export type Req = { tool: string; args: Record<string, unknown>; message: string };

function ArgValue({ v }: { v: unknown }) {
  if (Array.isArray(v)) {
    return (
      <div className="max-h-44 overflow-y-auto mt-1 flex flex-col gap-0.5 border-l-2 border-warning/40 pl-2.5">
        {v.map((item, i) => (
          <div key={i} className="break-all">
            {item !== null && typeof item === "object" && "src" in item
              ? `${(item as { src?: unknown }).src} → ${(item as { dst?: unknown }).dst}`
              : String(item)}
          </div>
        ))}
      </div>
    );
  }
  return <>{String(v)}</>;
}

export function ApprovalCard({
  request,
  onApprove,
  onReject,
}: {
  request: Req | null;
  onApprove: () => void;
  onReject: () => void;
}) {
  if (!request) return null;
  return (
    <div className="flex-none px-6 pb-3.5">
      <div className="max-w-[720px] mx-auto border border-warning bg-warning/8 rounded-[10px] p-4">
        <div className="flex items-center gap-2.5 mb-2">
          <TriangleAlert className="size-[18px] text-warning shrink-0" />
          <div className="font-semibold">Approval required</div>
          <div className="font-mono text-[11px] text-warning border border-warning rounded-full px-2.5 py-0.5">
            {request.tool}
          </div>
        </div>
        <div className="mb-2.5 text-pretty">{request.message}</div>
        <div className="font-mono text-xs leading-[1.7] bg-background border rounded-lg px-3.5 py-2.5 mb-3">
          {Object.entries(request.args).map(([k, v]) => (
            <div key={k} className="break-all">
              <span className="text-muted-foreground/60">
                {k}
                {Array.isArray(v) ? ` (${v.length} items)` : ""}
                {": "}
              </span>
              <ArgValue v={v} />
            </div>
          ))}
        </div>
        <div className="flex gap-2.5 items-center">
          <Button
            className="bg-warning text-background hover:bg-warning/90"
            onClick={onApprove}
          >
            Approve
          </Button>
          <Button variant="destructive" onClick={onReject}>
            Reject
          </Button>
          <span className="text-muted-foreground/60 text-xs ml-auto">
            The agent is paused until you decide.
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update empty-state suggestions**

In `frontend/src/components/ChatThread.tsx`, replace the `SUGGESTIONS` constant (lines 6–10) with:

```tsx
const SUGGESTIONS = [
  "List my Downloads",
  "Organize my Downloads: images into an Images folder, PDFs into Documents",
  "What's taking up space in my Documents folder?",
];
```

- [ ] **Step 3: Build (this is the frontend's test)**

Run: `cd "/d/Local Desktop/frontend" && export npm_config_cache="d:/Local Desktop/.npm-cache" && npm run build`
Expected: `tsc` passes, vite emits a single `dist/index.html` (~1.5 MB), zero errors.

- [ ] **Step 4: Commit**

```bash
cd "/d/Local Desktop" && git add frontend/src/components/ApprovalCard.tsx frontend/src/components/ChatThread.tsx && git commit -m "feat: approval card renders batch_move plans as a move list"
```

---

### Task 10: Full verification + real-model e2e

**Files:** none created — verification only.

- [ ] **Step 1: Full backend suite**

Run: `cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run pytest -v`
Expected: all tests pass (~40). The temp-dir `PermissionError` teardown warning is known-harmless.

- [ ] **Step 2: Scripted real-model smoke test (no GUI)**

Create a throwaway sandbox and drive one organize turn through the real graph + Ollama. Run from `backend/`:

```bash
cd "/d/Local Desktop/backend" && export UV_PYTHON_INSTALL_DIR="d:/Local Desktop/.uv/python" UV_CACHE_DIR="d:/Local Desktop/.uv/cache" && uv run python - <<'EOF'
import asyncio, tempfile, json
from pathlib import Path

sandbox = Path(tempfile.mkdtemp()) / "Downloads"
sandbox.mkdir()
for name in ("photo1.jpg", "photo2.jpg", "report.pdf"):
    (sandbox / name).write_text("x")

import agent.settings as settings_mod
real = settings_mod.load_settings()
class S:
    allowed_roots = [str(sandbox)]
    model = real.model
    dry_run = False
settings_mod.load_settings = lambda: S()
import agent.safety as safety_mod
safety_mod.load_settings = lambda: S()
import agent.graph as graph_mod
graph_mod.load_settings = lambda: S()

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage

g = graph_mod.build_graph(checkpointer=InMemorySaver())
cfg = {"configurable": {"thread_id": "smoke"}, "recursion_limit": 50}

async def main():
    out = await g.ainvoke({"messages": [HumanMessage(
        "Organize my Downloads: move all .jpg files into an Images subfolder."
    )]}, cfg)
    state = await g.aget_state(cfg)
    while state.next:  # approve any pending interrupt
        print("INTERRUPT:", json.dumps(state.tasks[0].interrupts[0].value, default=str)[:400])
        out = await g.ainvoke(Command(resume={"decision": "approve"}), cfg)
        state = await g.aget_state(cfg)
    print("FINAL:", out["messages"][-1].content[:400])
    print("Images/:", sorted(p.name for p in (sandbox / "Images").glob("*")) if (sandbox / "Images").exists() else "MISSING")

asyncio.run(main())
EOF
```

Expected: an `INTERRUPT:` line naming `batch_move` (or `move_file` twice — acceptable for a 2B model, but note it), a `FINAL:` summary, and `Images/: ['photo1.jpg', 'photo2.jpg']`.

- [ ] **Step 3: Manual GUI check (requires the user's display + Ollama)**

Launch with `run.cmd`, then verify:
1. Ask "Organize my Downloads: images into an Images folder" → approval card shows the moves list (scrollable, `src → dst` lines with item count).
2. Approve → files move; activity log shows the `batch_move` step with output.
3. Ask "create a file called shopping.md on my Desktop with a short grocery list" → file appears (no approval — new file).
4. Ask the same again → tool returns "already exists"; ask to overwrite → approval card appears.
5. Ask "delete <that file>" → approval card → approve → file lands in the Recycle Bin.
6. Toggle dry-run in settings → repeat a move → `[dry-run]` result, no approval prompt, nothing changes on disk.

- [ ] **Step 4: Update docs/tools.md status and push**

In `docs/tools.md`, change the Phase 0 heading to `## Phase 0 + build-step 1 — Shipped` and move the six Phase 1 rows plus `folder_stats`/`batch_move` rows into it (delete the then-empty Phase 1 section; renumber nothing else — phases keep their names).

```bash
cd "/d/Local Desktop" && git add docs/tools.md && git commit -m "docs: mark core file tools and batch_move as shipped" && git push origin main
```

---

## Self-review notes

- **Spec coverage:** all 8 new tools from build-order step 1 have tasks (2: read_file/file_info, 3: create_folder/copy_file, 4: write_file, 5: delete_file, 6: folder_stats, 7: batch_move); gate change (Task 1), prompt (Task 8), approval UI for batches (Task 9), e2e (Task 10). `batch_delete`, `search_files`, `search_content`, `find_duplicates` are Phase 2 remainder — deliberately NOT in this plan (next plan).
- **Type consistency:** `needs_approval(tool_name: str, args: dict | None)` used identically in Tasks 1/4/7; `sandbox` fixture returns `(root, settings)` everywhere; `_fmt_size` defined Task 2, reused Task 6; `moves: list[dict]` matches the gate payload Task 9 renders.
- **Known limitation carried forward:** the gate's partial approve/reject mix (multiple destructive calls in ONE model message) is still not fully handled — pre-existing `ponytail:` comment in `graph.py` stands. `batch_move` reduces the exposure (bulk = one call).
