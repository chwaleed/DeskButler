# Project Base + First 2 Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete permanent skeleton of a local Windows desktop AI agent — runtime spine, safety layer, LangGraph loop, and an end-to-end pywebview+React UI — shipping only two tools (`list_dir`, `move_file`) so that adding future tools is pure tool-writing.

**Architecture:** One Python process hosts a pywebview window (React UI) and the agent backend; Ollama runs separately over localhost. A single long-lived asyncio loop on a worker thread owns a LangGraph graph compiled once with a `SqliteSaver` checkpointer and a fixed `thread_id`. The graph is `call_model → safety_gate → tools → call_model`; the gate calls `interrupt()` on destructive tool calls so the UI can approve/reject. Guardrails (allowed-roots, recycle-bin delete, audit) live inside `safety.py` and are called from the tools, which are the trust boundary.

**Tech Stack:** Python 3.11+, **uv** (project + venv + runner), LangGraph, LangChain, `langchain-ollama` (`ChatOllama`), `langgraph-checkpoint-sqlite` (`SqliteSaver`), `pywebview`, `send2trash`, `pytest`; React + TypeScript + Vite frontend.

## Global Constraints

- Python 3.11+ (`requires-python = ">=3.11"`).
- **Backend project management is `uv`.** Use `uv init`, `uv add <pkg>`, `uv run <cmd>`. Dependencies live in `backend/pyproject.toml`; never write a `requirements.txt` or call `pip` directly.
- Model provider is local Ollama via `ChatOllama(model="qwen3.5:2b")`. Fallback sizes `qwen3.5:4b`/`qwen3.5:9b` — model name is the only change.
- Two tools only in this base: `list_dir`, `move_file`. Do not add others.
- Checkpointer is on-disk `SqliteSaver` at an app-data path; fixed `thread_id = "main"`.
- Destructive tool set is a module-level constant `DESTRUCTIVE = {"move_file"}` (grows to `{"move_file", "delete_file", "copy_file"}` later) — the single place tool destructiveness is declared.
- Guardrails are enforced **inside the tool functions** (the trust boundary), not only in the graph node.
- Never launch a subprocess for tools; tools are in-process `@tool` functions.
- Never call `asyncio.run()` per message; the one worker-thread loop is created once at startup.
- Tests cover `safety.py` and the interrupt/resume gate only. No UI or happy-path tests.
- All Python code targets Windows path semantics (this is a Windows-only app).

---

## File Structure

**Backend (`backend/`):**
- `pyproject.toml` — uv project + deps (created by `uv init` + `uv add`).
- `src/agent/__init__.py` — package marker.
- `src/agent/settings.py` — load/save app settings (allowed roots, model, dry-run) + app-data dir helper.
- `src/agent/safety.py` — `resolve_and_check`, `recycle_delete`, `audit`, `DESTRUCTIVE`, `is_destructive`, `dry_run` accessor.
- `src/agent/tools.py` — `list_dir`, `move_file` (`@tool`), `TOOLS`, `run_move` executor.
- `src/agent/graph.py` — graph definition + compile with checkpointer.
- `src/agent/runtime.py` — worker-thread loop, `run_turn`, `resume_turn`, `cancel`, event push hook.
- `src/agent/bridge.py` — pywebview `Api` class.
- `src/agent/prompts.py` — system prompt.
- `src/agent/health.py` — Ollama readiness check.
- `src/agent/main.py` — entry point (health check, window, loop startup).
- `tests/test_safety.py` — guardrail unit tests.
- `tests/test_gate.py` — interrupt/resume gate tests.

**Frontend (`frontend/`):** created via Vite; `src/api/bridge.ts`, `src/components/{ChatThread,ActionLog,ApprovalModal,SettingsPanel}.tsx`, `src/App.tsx`.

Each task below is independently testable and ends with a commit.

---

### Task 1: Backend project scaffold with uv

**Files:**
- Create: `backend/pyproject.toml` (via `uv init`)
- Create: `backend/src/agent/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a `uv`-managed project rooted at `backend/`; the `agent` package importable as `agent.*` when run with `uv run`; all runtime deps installed.

- [ ] **Step 1: Initialize the uv project**

Run from repo root:
```bash
cd backend && uv init --name agent --python 3.11 --no-workspace
```
Expected: creates `backend/pyproject.toml`, `backend/.python-version`, and a sample `hello.py` / `main.py`.

- [ ] **Step 2: Remove the sample module and create the package**

```bash
rm -f backend/main.py backend/hello.py
mkdir -p backend/src/agent backend/tests
```
Create `backend/src/agent/__init__.py`:
```python
"""Local desktop AI agent backend."""
```

- [ ] **Step 3: Point the package at src/ layout**

Edit `backend/pyproject.toml` — ensure it contains (merge into the generated file):
```toml
[project]
name = "agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[tool.hatch.build.targets.wheel]
packages = ["src/agent"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Add runtime and dev dependencies**

```bash
cd backend
uv add langgraph langchain langchain-ollama langgraph-checkpoint-sqlite pywebview send2trash
uv add --dev pytest
```
Expected: `pyproject.toml` `dependencies` populated; `uv.lock` created; `.venv/` created.

- [ ] **Step 5: Verify the environment imports**

Run:
```bash
cd backend && uv run python -c "import langgraph, langchain_ollama, send2trash, webview; from langgraph.checkpoint.sqlite import SqliteSaver; from langgraph.types import interrupt, Command; print('ok')"
```
Expected: prints `ok` with no ImportError.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/.python-version backend/src/agent/__init__.py
git commit -m "chore: scaffold backend with uv and src layout"
```

---

### Task 2: Settings + app-data directory

**Files:**
- Create: `backend/src/agent/settings.py`
- Test: (covered indirectly; no dedicated test — trivial IO, per Global Constraints test scope)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `app_data_dir() -> Path` — returns (and creates) `%LOCALAPPDATA%\ai-desktop-agent`.
  - `Settings` dataclass: `allowed_roots: list[str]`, `model: str = "qwen3.5:2b"`, `dry_run: bool = False`.
  - `load_settings() -> Settings` — reads `settings.json` from app-data, or returns defaults (allowed_roots = user Downloads + Documents).
  - `save_settings(s: Settings) -> None` — writes `settings.json`.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/settings.py`:
```python
"""App settings + app-data directory. Backend-owned; the UI edits via the bridge."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "ai-desktop-agent"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_roots() -> list[str]:
    home = Path.home()
    return [str(home / "Downloads"), str(home / "Documents")]


@dataclass
class Settings:
    allowed_roots: list[str] = field(default_factory=_default_roots)
    model: str = "qwen3.5:2b"
    dry_run: bool = False


def _settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> Settings:
    p = _settings_path()
    if not p.exists():
        return Settings()
    data = json.loads(p.read_text(encoding="utf-8"))
    return Settings(
        allowed_roots=data.get("allowed_roots", _default_roots()),
        model=data.get("model", "qwen3.5:2b"),
        dry_run=data.get("dry_run", False),
    )


def save_settings(s: Settings) -> None:
    _settings_path().write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
```

- [ ] **Step 2: Smoke-check it runs**

Run:
```bash
cd backend && uv run python -c "from agent.settings import load_settings, app_data_dir; print(app_data_dir()); print(load_settings())"
```
Expected: prints the app-data path and a `Settings(...)` with two allowed roots.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/settings.py
git commit -m "feat: settings and app-data directory"
```

---

### Task 3: Allowed-roots canonicalization (highest-risk guardrail)

**Files:**
- Create: `backend/src/agent/safety.py` (partial — `resolve_and_check` + `PathNotAllowed`)
- Test: `backend/tests/test_safety.py`

**Interfaces:**
- Consumes: `agent.settings.load_settings`.
- Produces:
  - `class PathNotAllowed(Exception)`.
  - `resolve_and_check(path: str, roots: list[str] | None = None) -> Path` — canonicalizes, rejects UNC/device prefixes, requires the resolved path be inside an allowed root (uses `load_settings().allowed_roots` when `roots` is None). Raises `PathNotAllowed` otherwise.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_safety.py`:
```python
import pytest
from pathlib import Path
from agent.safety import resolve_and_check, PathNotAllowed


def test_path_inside_root_is_allowed(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("x")
    out = resolve_and_check(str(target), roots=[str(root)])
    assert out == target.resolve()


def test_path_outside_root_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x")
    with pytest.raises(PathNotAllowed):
        resolve_and_check(str(outside), roots=[str(root)])


def test_dotdot_traversal_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    escape = str(root / ".." / "secret.txt")
    with pytest.raises(PathNotAllowed):
        resolve_and_check(escape, roots=[str(root)])


def test_case_insensitive_match_is_allowed(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("x")
    # Windows path compare is case-insensitive; upper-cased root must still match.
    out = resolve_and_check(str(target), roots=[str(root).upper()])
    assert out == target.resolve()


def test_unc_path_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_and_check(r"\\server\share\file.txt", roots=[str(root)])


def test_device_prefix_is_rejected(tmp_path):
    root = tmp_path / "Downloads"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        resolve_and_check(r"\\?\C:\Windows\system32\config", roots=[str(root)])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && uv run pytest tests/test_safety.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.safety'` (or ImportError for the names).

- [ ] **Step 3: Write minimal implementation**

Create `backend/src/agent/safety.py`:
```python
"""Guardrails — the trust boundary for anything the agent touches on disk."""
from __future__ import annotations

from pathlib import Path

from agent.settings import load_settings


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/test_safety.py -v
```
Expected: PASS (6 passed).

Note: `..` traversal, symlinks, and 8.3 short names all normalize through `Path.resolve()`, so the containment check catches them; the dedicated `test_dotdot_traversal_is_rejected` proves it.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/safety.py backend/tests/test_safety.py
git commit -m "feat: allowed-roots canonicalization with tests"
```

---

### Task 4: Recycle-bin delete + audit log

**Files:**
- Modify: `backend/src/agent/safety.py` (add `recycle_delete`, `audit`)
- Test: `backend/tests/test_safety.py` (add tests)

**Interfaces:**
- Consumes: `send2trash`, `agent.settings.app_data_dir`.
- Produces:
  - `recycle_delete(path: Path) -> None` — sends a file to the Recycle Bin via `send2trash`. (Built now for the future `delete_file` tool; unit-tested now.)
  - `audit(entry: dict) -> None` — appends a JSON line to `<app-data>/audit.log`.

- [ ] **Step 1: Write the failing tests (append to test_safety.py)**

Add to `backend/tests/test_safety.py`:
```python
import json
from agent.safety import recycle_delete, audit


def test_recycle_delete_removes_file(tmp_path, monkeypatch):
    calls = {}
    def fake_send2trash(p):
        calls["path"] = p
    monkeypatch.setattr("agent.safety.send2trash", fake_send2trash)
    f = tmp_path / "gone.txt"
    f.write_text("x")
    recycle_delete(f)
    assert calls["path"] == str(f)


def test_audit_appends_json_line(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.safety.app_data_dir", lambda: tmp_path)
    audit({"tool": "move_file", "result": "ok"})
    audit({"tool": "list_dir", "result": "ok"})
    lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "move_file"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && uv run pytest tests/test_safety.py -k "recycle or audit" -v
```
Expected: FAIL — `ImportError: cannot import name 'recycle_delete'`.

- [ ] **Step 3: Write minimal implementation (append to safety.py)**

Add to the top imports of `backend/src/agent/safety.py`:
```python
import json

from send2trash import send2trash

from agent.settings import app_data_dir, load_settings
```
(Replace the existing single `from agent.settings import load_settings` line with the combined import above.)

Append to `backend/src/agent/safety.py`:
```python
def recycle_delete(path: Path) -> None:
    """Send a file to the Recycle Bin (recoverable), never a permanent delete."""
    send2trash(str(path))


def audit(entry: dict) -> None:
    """Append one JSON line to the persistent audit log in app-data."""
    line = json.dumps(entry, ensure_ascii=False)
    with (app_data_dir() / "audit.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/test_safety.py -v
```
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/safety.py backend/tests/test_safety.py
git commit -m "feat: recycle-bin delete and audit log with tests"
```

---

### Task 5: Destructive-set + dry-run accessor

**Files:**
- Modify: `backend/src/agent/safety.py` (add `DESTRUCTIVE`, `is_destructive`, `dry_run`)

**Interfaces:**
- Consumes: `agent.settings.load_settings`.
- Produces:
  - `DESTRUCTIVE: set[str]` — currently `{"move_file"}`.
  - `is_destructive(tool_name: str) -> bool`.
  - `dry_run() -> bool` — reads the current setting.

- [ ] **Step 1: Append to safety.py**

Append to `backend/src/agent/safety.py`:
```python
# The single place tool destructiveness is declared. Add "delete_file", "copy_file" later.
DESTRUCTIVE: set[str] = {"move_file"}


def is_destructive(tool_name: str) -> bool:
    return tool_name in DESTRUCTIVE


def dry_run() -> bool:
    return load_settings().dry_run
```

- [ ] **Step 2: Smoke-check**

Run:
```bash
cd backend && uv run python -c "from agent.safety import is_destructive, dry_run, DESTRUCTIVE; print(DESTRUCTIVE, is_destructive('move_file'), is_destructive('list_dir'), dry_run())"
```
Expected: prints `{'move_file'} True False False`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/safety.py
git commit -m "feat: destructive-tool set and dry-run accessor"
```

---

### Task 6: The two tools (`list_dir`, `move_file`)

**Files:**
- Create: `backend/src/agent/tools.py`

**Interfaces:**
- Consumes: `agent.safety.{resolve_and_check, audit, PathNotAllowed}`, `langchain_core.tools.tool`.
- Produces:
  - `list_dir` (`@tool`) — `list_dir(path: str) -> str`.
  - `move_file` (`@tool`) — `move_file(src: str, dst: str) -> str`. Validates, rejects exe/DLL dst, fails if dst exists. **Does not itself pause** — the gate node owns the interrupt; this function is the executor that runs on approval.
  - `TOOLS: list` — `[list_dir, move_file]`.
  - `FORBIDDEN_DST_EXT: set[str]`.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/tools.py`:
```python
"""In-process agent tools. Guardrails run here — the trust boundary."""
from __future__ import annotations

import shutil
from pathlib import Path

from langchain_core.tools import tool

from agent.safety import PathNotAllowed, audit, resolve_and_check

FORBIDDEN_DST_EXT = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".scr", ".lnk"}


@tool
def list_dir(path: str) -> str:
    """List the files and folders in a directory. Read-only."""
    try:
        target = resolve_and_check(path)
    except PathNotAllowed as e:
        audit({"tool": "list_dir", "path": path, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if not target.is_dir():
        return f"Not a directory: {target}"
    entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
    audit({"tool": "list_dir", "path": str(target), "result": "ok", "count": len(entries)})
    return "\n".join(entries) if entries else "(empty)"


@tool
def move_file(src: str, dst: str) -> str:
    """Move a file from src to dst. Destructive — requires approval."""
    try:
        src_p = resolve_and_check(src)
        dst_p = resolve_and_check(dst)
    except PathNotAllowed as e:
        audit({"tool": "move_file", "src": src, "dst": dst, "result": "denied", "error": str(e)})
        return f"Denied: {e}"
    if dst_p.suffix.lower() in FORBIDDEN_DST_EXT:
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "forbidden extension"})
        return f"Denied: cannot move to an executable/script destination ({dst_p.suffix})"
    if dst_p.exists():
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "denied", "error": "destination exists"})
        return f"Denied: destination already exists ({dst_p})"
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_p), str(dst_p))
    audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "ok"})
    return f"Moved {src_p.name} to {dst_p}"


TOOLS = [list_dir, move_file]
```

- [ ] **Step 2: Smoke-check the tools run**

Run:
```bash
cd backend && uv run python -c "from agent.tools import TOOLS; print([t.name for t in TOOLS])"
```
Expected: prints `['list_dir', 'move_file']`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/tools.py
git commit -m "feat: list_dir and move_file tools with in-tool guardrails"
```

---

### Task 7: System prompt

**Files:**
- Create: `backend/src/agent/prompts.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT: str`.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/prompts.py`:
```python
"""System prompt for the agent."""

SYSTEM_PROMPT = (
    "You are a local file assistant on the user's Windows computer. "
    "You can list directories and move files using the provided tools. "
    "Only operate inside the user's allowed folders. "
    "Before moving files, make sure the source and destination are clear. "
    "When you have finished the user's request, reply with a short plain-language summary. "
    "If a tool returns 'Denied', explain the reason to the user; do not retry blindly."
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/agent/prompts.py
git commit -m "feat: system prompt"
```

---

### Task 8: The graph — model, safety gate, tools, compiled with checkpointer

**Files:**
- Create: `backend/src/agent/graph.py`
- Test: `backend/tests/test_gate.py`

**Interfaces:**
- Consumes: `agent.tools.TOOLS`, `agent.safety.{is_destructive, dry_run}`, `agent.prompts.SYSTEM_PROMPT`, `agent.settings.load_settings`.
- Produces:
  - `build_graph(model=None, checkpointer=None)` — returns a compiled graph. `model` defaults to `ChatOllama(model=<settings.model>)`; `checkpointer` defaults to a `SqliteSaver` at `<app-data>/checkpoints.db`. Injectable for tests.
  - Graph nodes named `"call_model"`, `"safety_gate"`, `"tools"`.
  - The gate calls `interrupt({...})` for destructive tool calls when not in dry-run; on resume it reads `{"decision": "approve"|"reject"}`. On reject it appends a `ToolMessage` for each rejected call so the model sees the rejection, and routes to `call_model` instead of `tools`.

**Design note:** The gate handles a message that mixes safe and destructive tool calls. It interrupts once per destructive call (per-tool-call granularity). Rejected calls get a synthetic `ToolMessage`; if *all* destructive calls are rejected and there are no remaining tool calls to run, it routes back to the model.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_gate.py`:
```python
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.graph import build_graph


def _model_that_moves_then_answers():
    """Fake model: first turn requests a move_file tool call, second turn answers."""
    move_call = AIMessage(
        content="",
        tool_calls=[{"name": "move_file", "args": {"src": "a", "dst": "b"}, "id": "call1"}],
    )
    done = AIMessage(content="Done.")
    return GenericFakeChatModel(messages=iter([move_call, done]))


def test_destructive_call_pauses_for_approval(monkeypatch):
    # Stub the tool executor so no real filesystem work happens.
    monkeypatch.setattr("agent.tools.shutil.move", lambda a, b: None)
    monkeypatch.setattr("agent.safety.resolve_and_check", lambda p, roots=None: __import__("pathlib").Path(p))
    monkeypatch.setattr("agent.safety.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    result = graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    # Graph should be interrupted, not finished.
    state = graph.get_state(config)
    assert state.next  # there is a pending node -> we are paused
    assert state.tasks and state.tasks[0].interrupts  # an interrupt is outstanding


def test_reject_short_circuits_without_moving(monkeypatch):
    moved = {"called": False}
    def fake_move(a, b):
        moved["called"] = True
    monkeypatch.setattr("agent.tools.shutil.move", fake_move)
    monkeypatch.setattr("agent.safety.resolve_and_check", lambda p, roots=None: __import__("pathlib").Path(p))
    monkeypatch.setattr("agent.safety.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    final = graph.invoke(Command(resume={"decision": "reject"}), config)
    assert moved["called"] is False
    # The conversation continued to a final answer after rejection.
    assert any(getattr(m, "content", "") == "Done." for m in final["messages"])


def test_approve_executes_the_move(monkeypatch):
    moved = {"called": False}
    def fake_move(a, b):
        moved["called"] = True
    monkeypatch.setattr("agent.tools.shutil.move", fake_move)
    monkeypatch.setattr("agent.tools.Path.exists", lambda self: False)
    monkeypatch.setattr("agent.safety.resolve_and_check", lambda p, roots=None: __import__("pathlib").Path(p))
    monkeypatch.setattr("agent.safety.dry_run", lambda: False)

    graph = build_graph(model=_model_that_moves_then_answers(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t3"}}
    graph.invoke({"messages": [HumanMessage("move a to b")]}, config)
    final = graph.invoke(Command(resume={"decision": "approve"}), config)
    assert moved["called"] is True
    assert any(getattr(m, "content", "") == "Done." for m in final["messages"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && uv run pytest tests/test_gate.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.graph'`.

- [ ] **Step 3: Write the graph**

Create `backend/src/agent/graph.py`:
```python
"""LangGraph agent loop: call_model -> safety_gate -> tools -> call_model."""
from __future__ import annotations

import sqlite3
from typing import Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from agent.prompts import SYSTEM_PROMPT
from agent.safety import dry_run, is_destructive
from agent.settings import app_data_dir, load_settings
from agent.tools import TOOLS


def _default_model():
    from langchain_ollama import ChatOllama

    return ChatOllama(model=load_settings().model)


def _default_checkpointer():
    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(str(app_data_dir() / "checkpoints.db"), check_same_thread=False)
    return SqliteSaver(conn)


def build_graph(model=None, checkpointer=None):
    model = model if model is not None else _default_model()
    checkpointer = checkpointer if checkpointer is not None else _default_checkpointer()
    bound = model.bind_tools(TOOLS)

    def call_model(state: MessagesState):
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(SYSTEM_PROMPT), *msgs]
        return {"messages": [bound.invoke(msgs)]}

    def route_after_model(state: MessagesState) -> Literal["safety_gate", "__end__"]:
        return "safety_gate" if state["messages"][-1].tool_calls else END

    def safety_gate(state: MessagesState):
        last = state["messages"][-1]
        rejections = []
        for call in last.tool_calls:
            if is_destructive(call["name"]) and not dry_run():
                decision = interrupt(
                    {"tool": call["name"], "args": call["args"], "message": f"Approve {call['name']}?"}
                )
                if isinstance(decision, dict) and decision.get("decision") == "reject":
                    rejections.append(
                        ToolMessage(content="Rejected by user.", tool_call_id=call["id"])
                    )
        # If every tool call was rejected, feed the rejections back to the model instead of executing.
        if rejections and len(rejections) == len(last.tool_calls):
            return {"messages": rejections}
        return {"messages": rejections}  # partial rejections still recorded; survivors run in ToolNode

    def route_after_gate(state: MessagesState) -> Literal["tools", "call_model"]:
        # If the last message is a ToolMessage (all rejected), skip ToolNode and let the model react.
        last = state["messages"][-1]
        if isinstance(last, ToolMessage):
            return "call_model"
        return "tools"

    g = StateGraph(MessagesState)
    g.add_node("call_model", call_model)
    g.add_node("safety_gate", safety_gate)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "call_model")
    g.add_conditional_edges("call_model", route_after_model, {"safety_gate": "safety_gate", END: END})
    g.add_conditional_edges("safety_gate", route_after_gate, {"tools": "tools", "call_model": "call_model"})
    g.add_edge("tools", "call_model")
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest tests/test_gate.py -v
```
Expected: PASS (3 passed). If `GenericFakeChatModel` import path differs in the installed langchain version, run `uv run python -c "from langchain_core.language_models.fake_chat_models import GenericFakeChatModel"` to confirm; adjust the import to `langchain_core.language_models.fake` if needed.

- [ ] **Step 5: Run the full test suite**

Run:
```bash
cd backend && uv run pytest -v
```
Expected: PASS (11 passed — 8 safety + 3 gate).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent/graph.py backend/tests/test_gate.py
git commit -m "feat: agent graph with safety-gate interrupt and tests"
```

---

### Task 9: Ollama health check

**Files:**
- Create: `backend/src/agent/health.py`

**Interfaces:**
- Consumes: `urllib` (stdlib), `agent.settings.load_settings`.
- Produces: `check_ollama() -> tuple[bool, str]` — returns `(ok, message)`. Ok only if the daemon responds on `/api/tags` and the configured model is present.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/health.py`:
```python
"""Startup readiness check for the local Ollama daemon."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from agent.settings import load_settings


def check_ollama(base_url: str = "http://localhost:11434") -> tuple[bool, str]:
    model = load_settings().model
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False, "Ollama is not running. Start it, then reopen the app."
    names = {m.get("name", "").split(":")[0] for m in data.get("models", [])}
    tags = {m.get("name", "") for m in data.get("models", [])}
    if model in tags or model.split(":")[0] in names:
        return True, "ok"
    return False, f"Model '{model}' is not installed. Run: ollama pull {model}"
```

- [ ] **Step 2: Smoke-check (no assertion on result — depends on local Ollama)**

Run:
```bash
cd backend && uv run python -c "from agent.health import check_ollama; print(check_ollama())"
```
Expected: prints a `(bool, str)` tuple. Either `(True, 'ok')` if Ollama+model present, or a `(False, ...)` message otherwise — both are acceptable.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/health.py
git commit -m "feat: ollama readiness check"
```

---

### Task 10: Runtime spine — worker-thread loop + turn orchestration

**Files:**
- Create: `backend/src/agent/runtime.py`

**Interfaces:**
- Consumes: `agent.graph.build_graph`, `asyncio`, `threading`.
- Produces a `Runtime` class:
  - `Runtime(emit)` — `emit: Callable[[dict], None]` is how the runtime pushes events to the UI (bridge supplies it).
  - `start() -> None` — spins the worker thread + event loop, builds the graph once.
  - `send(text: str) -> str` — returns a `turn_id`, schedules a turn; rejects if one is already running (returns `"busy"`).
  - `resume(decision: dict) -> None` — resumes a paused turn.
  - `cancel() -> None` — sets a cancel flag (checked between turns; best-effort).
  - fixed `thread_id = "main"`.

**Design note:** Events emitted: `{"type": "step", "turn_id", "text"}` per tool/step, `{"type": "approval", "turn_id", "request"}` on interrupt, `{"type": "final", "turn_id", "text"}` at end, `{"type": "error", "turn_id", "text"}` on failure. The bridge turns these into `window.onAgentEvent(...)`.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/runtime.py`:
```python
"""The single long-lived asyncio loop that owns the graph. All Api calls route here."""
from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Callable

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent.graph import build_graph

THREAD_ID = "main"


class Runtime:
    def __init__(self, emit: Callable[[dict], None]):
        self._emit = emit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._graph = None
        self._busy = False
        self._current_turn: str | None = None
        self._config = {"configurable": {"thread_id": THREAD_ID}}

    def start(self) -> None:
        ready = threading.Event()

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._graph = build_graph()
            ready.set()
            self._loop.run_forever()

        threading.Thread(target=run_loop, daemon=True, name="agent-loop").start()
        ready.wait(timeout=30)

    def send(self, text: str) -> str:
        if self._busy:
            return "busy"
        turn_id = uuid.uuid4().hex
        self._current_turn = turn_id
        self._busy = True
        asyncio.run_coroutine_threadsafe(self._run_turn(turn_id, text), self._loop)
        return turn_id

    def resume(self, decision: dict) -> None:
        if self._current_turn is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._drive(self._current_turn, Command(resume=decision)), self._loop
        )

    def cancel(self) -> None:
        # Best-effort: mark not busy so the UI unlocks; the in-flight step still completes.
        self._busy = False
        self._current_turn = None

    async def _run_turn(self, turn_id: str, text: str) -> None:
        await self._drive(turn_id, {"messages": [HumanMessage(text)]})

    async def _drive(self, turn_id: str, payload) -> None:
        try:
            async for event in self._graph.astream_events(payload, self._config, version="v2"):
                kind = event.get("event")
                if kind == "on_tool_start":
                    name = event.get("name", "tool")
                    self._emit({"type": "step", "turn_id": turn_id, "text": f"running {name}…"})
            # After the stream, inspect state: paused (interrupt) or finished.
            state = self._graph.get_state(self._config)
            if state.tasks and any(t.interrupts for t in state.tasks):
                intr = next(t.interrupts[0] for t in state.tasks if t.interrupts)
                self._emit({"type": "approval", "turn_id": turn_id, "request": intr.value})
                return
            final = state.values["messages"][-1]
            self._emit({"type": "final", "turn_id": turn_id, "text": getattr(final, "content", "")})
            self._busy = False
        except Exception as e:  # surface as a chat bubble, never crash the loop
            self._emit({"type": "error", "turn_id": turn_id, "text": str(e)})
            self._busy = False
```

- [ ] **Step 2: Smoke-check import**

Run:
```bash
cd backend && uv run python -c "from agent.runtime import Runtime, THREAD_ID; print('ok', THREAD_ID)"
```
Expected: prints `ok main`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/runtime.py
git commit -m "feat: runtime spine with worker-thread loop and turn orchestration"
```

---

### Task 11: pywebview bridge (`Api`)

**Files:**
- Create: `backend/src/agent/bridge.py`

**Interfaces:**
- Consumes: `agent.runtime.Runtime`, `agent.settings.{load_settings, save_settings, Settings}`.
- Produces an `Api` class exposed to JS:
  - `send_message(text: str) -> str` (returns turn_id or `"busy"`).
  - `approve(decision: dict) -> None`.
  - `cancel() -> None`.
  - `get_settings() -> dict` / `save_settings(data: dict) -> None`.
  - `set_window(window)` — receives the pywebview window so the runtime's `emit` can call `evaluate_js`.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/bridge.py`:
```python
"""pywebview Api: the JS<->Python boundary. Methods run on pywebview's own threads."""
from __future__ import annotations

import json
from dataclasses import asdict

from agent.runtime import Runtime
from agent.settings import Settings, load_settings, save_settings


class Api:
    def __init__(self):
        self._window = None
        self._runtime = Runtime(emit=self._emit)

    def set_window(self, window) -> None:
        self._window = window
        self._runtime.start()

    def _emit(self, event: dict) -> None:
        if self._window is not None:
            payload = json.dumps(event)
            self._window.evaluate_js(f"window.onAgentEvent({payload})")

    # --- exposed to JS ---
    def send_message(self, text: str) -> str:
        return self._runtime.send(text)

    def approve(self, decision: dict) -> None:
        self._runtime.resume(decision)

    def cancel(self) -> None:
        self._runtime.cancel()

    def get_settings(self) -> dict:
        return asdict(load_settings())

    def save_settings(self, data: dict) -> None:
        save_settings(Settings(**data))
```

- [ ] **Step 2: Smoke-check import**

Run:
```bash
cd backend && uv run python -c "from agent.bridge import Api; a = Api(); print([m for m in dir(a) if not m.startswith('_')])"
```
Expected: lists `approve, cancel, get_settings, save_settings, send_message, set_window`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent/bridge.py
git commit -m "feat: pywebview Api bridge"
```

---

### Task 12: Entry point (`main.py`)

**Files:**
- Create: `backend/src/agent/main.py`

**Interfaces:**
- Consumes: `webview`, `agent.bridge.Api`, `agent.health.check_ollama`.
- Produces: `main() -> None` and `if __name__ == "__main__"` guard. Loads the built frontend (`frontend/dist/index.html`) if present, else a small placeholder HTML so the window opens before the frontend exists.

- [ ] **Step 1: Write the module**

Create `backend/src/agent/main.py`:
```python
"""Entry point: readiness check, create the window, start the runtime."""
from __future__ import annotations

from pathlib import Path

import webview

from agent.bridge import Api
from agent.health import check_ollama

_PLACEHOLDER = "<html><body style='font-family:sans-serif;padding:2rem'>Backend running. Build the frontend to see the UI.</body></html>"


def _frontend_entry() -> str:
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"
    return str(dist) if dist.exists() else _PLACEHOLDER


def main() -> None:
    api = Api()
    ok, message = check_ollama()
    entry = _frontend_entry()
    window = webview.create_window("AI Desktop Agent", entry, js_api=api, width=900, height=700)
    api.set_window(window)
    if not ok:
        # Surface the readiness problem as soon as the DOM is ready.
        def notify():
            import json
            window.evaluate_js(f"window.onAgentEvent && window.onAgentEvent({json.dumps({'type':'error','turn_id':'startup','text':message})})")
        window.events.loaded += notify
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-check import (do not start the window in CI)**

Run:
```bash
cd backend && uv run python -c "from agent.main import main, _frontend_entry; print('ok'); print(_frontend_entry()[:40])"
```
Expected: prints `ok` and the first chars of either the dist path or the placeholder HTML.

- [ ] **Step 3: Manual run check (local, has a display)**

Run:
```bash
cd backend && uv run python -m agent.main
```
Expected: a desktop window opens showing the placeholder (or the frontend if built). Close it to end. If Ollama is down, an error event fires (not yet visible without the frontend — that's fine at this task).

- [ ] **Step 4: Commit**

```bash
git add backend/src/agent/main.py
git commit -m "feat: application entry point"
```

---

### Task 13: Frontend scaffold (Vite + React + TS) and bridge client

**Files:**
- Create: `frontend/` (via Vite)
- Create: `frontend/src/api/bridge.ts`

**Interfaces:**
- Consumes: `window.pywebview.api` (injected by pywebview at runtime), `window.onAgentEvent` (called by the backend).
- Produces `frontend/src/api/bridge.ts`:
  - `type AgentEvent = { type: "step" | "approval" | "final" | "error"; turn_id: string; text?: string; request?: any }`.
  - `sendMessage(text: string): Promise<string>`.
  - `approve(decision: { decision: "approve" | "reject" }): Promise<void>`.
  - `cancel(): Promise<void>`.
  - `getSettings(): Promise<any>` / `saveSettings(data: any): Promise<void>`.
  - `onAgentEvent(handler: (e: AgentEvent) => void): void` — registers the global.

- [ ] **Step 1: Scaffold the Vite app**

Run from repo root:
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```
Expected: `frontend/` created with a working React+TS template; `node_modules` installed.

- [ ] **Step 2: Configure Vite for relative asset paths (needed by pywebview file:// loading)**

Edit `frontend/vite.config.ts` — add `base: "./"`:
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
});
```

- [ ] **Step 3: Write the bridge client**

Create `frontend/src/api/bridge.ts`:
```typescript
export type AgentEvent = {
  type: "step" | "approval" | "final" | "error";
  turn_id: string;
  text?: string;
  request?: { tool: string; args: Record<string, unknown>; message: string };
};

declare global {
  interface Window {
    pywebview: { api: Record<string, (...args: unknown[]) => Promise<unknown>> };
    onAgentEvent?: (e: AgentEvent) => void;
  }
}

export function sendMessage(text: string): Promise<string> {
  return window.pywebview.api.send_message(text) as Promise<string>;
}
export function approve(decision: { decision: "approve" | "reject" }): Promise<void> {
  return window.pywebview.api.approve(decision) as Promise<void>;
}
export function cancel(): Promise<void> {
  return window.pywebview.api.cancel() as Promise<void>;
}
export function getSettings(): Promise<any> {
  return window.pywebview.api.get_settings() as Promise<any>;
}
export function saveSettings(data: any): Promise<void> {
  return window.pywebview.api.save_settings(data) as Promise<void>;
}
export function onAgentEvent(handler: (e: AgentEvent) => void): void {
  window.onAgentEvent = handler;
}
```

- [ ] **Step 4: Verify it builds**

Run:
```bash
cd frontend && npm run build
```
Expected: `frontend/dist/` produced with `index.html` using relative (`./assets/...`) paths.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig*.json frontend/index.html frontend/src
git commit -m "feat: frontend scaffold and bridge client"
```

---

### Task 14: UI thin slice — chat, action log, approval modal, settings

**Files:**
- Create: `frontend/src/components/ChatThread.tsx`
- Create: `frontend/src/components/ActionLog.tsx`
- Create: `frontend/src/components/ApprovalModal.tsx`
- Create: `frontend/src/components/SettingsPanel.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: everything from `frontend/src/api/bridge.ts`.
- Produces: a working App that wires one full round trip. **This is a functional slice, not the final visual design** — plain markup, no styling decisions (those come from the separate UI design guide + design phase). Distinguish chat messages from action-log steps (the UI design guide's non-negotiable) by rendering them in two separate regions.

- [ ] **Step 1: Write ChatThread**

Create `frontend/src/components/ChatThread.tsx`:
```tsx
type Msg = { role: "user" | "agent"; text: string };

export function ChatThread({ messages }: { messages: Msg[] }) {
  return (
    <div aria-label="chat">
      {messages.map((m, i) => (
        <div key={i} data-role={m.role}>
          <strong>{m.role === "user" ? "You" : "Agent"}:</strong> {m.text}
        </div>
      ))}
    </div>
  );
}
export type { Msg };
```

- [ ] **Step 2: Write ActionLog**

Create `frontend/src/components/ActionLog.tsx`:
```tsx
export function ActionLog({ steps }: { steps: string[] }) {
  return (
    <div aria-label="action-log">
      <h3>Activity</h3>
      <ul>
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: Write ApprovalModal**

Create `frontend/src/components/ApprovalModal.tsx`:
```tsx
type Req = { tool: string; args: Record<string, unknown>; message: string };

export function ApprovalModal({
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
    <div role="dialog" aria-label="approval" style={{ border: "1px solid", padding: 16 }}>
      <p>{request.message}</p>
      <p>
        <strong>{request.tool}</strong>: {JSON.stringify(request.args)}
      </p>
      <button onClick={onApprove}>Approve</button>
      <button onClick={onReject}>Reject</button>
    </div>
  );
}
export type { Req };
```

- [ ] **Step 4: Write SettingsPanel**

Create `frontend/src/components/SettingsPanel.tsx`:
```tsx
import { useEffect, useState } from "react";
import { getSettings, saveSettings } from "../api/bridge";

export function SettingsPanel() {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    getSettings().then(setS);
  }, []);
  if (!s) return null;
  return (
    <div aria-label="settings">
      <h3>Settings</h3>
      <label>
        Dry-run{" "}
        <input
          type="checkbox"
          checked={s.dry_run}
          onChange={(e) => {
            const next = { ...s, dry_run: e.target.checked };
            setS(next);
            saveSettings(next);
          }}
        />
      </label>
      <div>Allowed roots: {s.allowed_roots.join(", ")}</div>
      <div>Model: {s.model}</div>
    </div>
  );
}
```

- [ ] **Step 5: Wire it all in App.tsx**

Replace `frontend/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import { ChatThread, type Msg } from "./components/ChatThread";
import { ActionLog } from "./components/ActionLog";
import { ApprovalModal, type Req } from "./components/ApprovalModal";
import { SettingsPanel } from "./components/SettingsPanel";
import { approve, cancel, onAgentEvent, sendMessage, type AgentEvent } from "./api/bridge";

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [steps, setSteps] = useState<string[]>([]);
  const [approval, setApproval] = useState<Req | null>(null);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");

  useEffect(() => {
    onAgentEvent((e: AgentEvent) => {
      if (e.type === "step") setSteps((s) => [...s, e.text ?? ""]);
      else if (e.type === "approval") setApproval(e.request ?? null);
      else if (e.type === "final") {
        setMessages((m) => [...m, { role: "agent", text: e.text ?? "" }]);
        setBusy(false);
      } else if (e.type === "error") {
        setMessages((m) => [...m, { role: "agent", text: `Error: ${e.text}` }]);
        setBusy(false);
      }
    });
  }, []);

  async function submit() {
    if (!input.trim() || busy) return;
    setMessages((m) => [...m, { role: "user", text: input }]);
    setBusy(true);
    const turnId = await sendMessage(input);
    setInput("");
    if (turnId === "busy") setBusy(false);
  }

  function decide(decision: "approve" | "reject") {
    setApproval(null);
    approve({ decision });
  }

  return (
    <div style={{ display: "flex", gap: 16, padding: 16 }}>
      <div style={{ flex: 2 }}>
        <ChatThread messages={messages} />
        <ApprovalModal request={approval} onApprove={() => decide("approve")} onReject={() => decide("reject")} />
        <div>
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} placeholder="Ask me to list or move files…" />
          <button onClick={submit} disabled={busy}>Send</button>
          {busy && <button onClick={() => { cancel(); setBusy(false); }}>Stop</button>}
        </div>
      </div>
      <div style={{ flex: 1 }}>
        <ActionLog steps={steps} />
        <SettingsPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Build the frontend**

Run:
```bash
cd frontend && npm run build
```
Expected: `frontend/dist/` rebuilt with the new components, no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: UI thin slice — chat, action log, approval modal, settings"
```

---

### Task 15: End-to-end manual verification + README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything.
- Produces: run instructions; a verified end-to-end round trip.

- [ ] **Step 1: Prep Ollama**

Run (once, local):
```bash
ollama pull qwen3.5:2b
```
Expected: model downloaded. Ensure `ollama serve` is running (Ollama's tray app does this).

- [ ] **Step 2: Build frontend, launch app**

Run:
```bash
cd frontend && npm run build
cd ../backend && uv run python -m agent.main
```
Expected: window opens with the chat UI.

- [ ] **Step 3: Verify the read path**

In the app, type: `list my Downloads folder`.
Expected: the action log shows a `running list_dir…` step; the chat shows a listing/summary. No approval modal (read-only).

- [ ] **Step 4: Verify the destructive path (approve)**

Put a test file in Downloads first (e.g. `test.txt`). Type: `move test.txt from Downloads into Documents`.
Expected: an approval modal appears showing `move_file` and the src/dst args. Click **Approve** → the file moves; chat confirms. Check `%LOCALAPPDATA%\ai-desktop-agent\audit.log` contains a `move_file … "result": "ok"` line.

- [ ] **Step 5: Verify the destructive path (reject)**

Type another move command. When the modal appears, click **Reject**.
Expected: the file does NOT move; the agent replies acknowledging the rejection. `audit.log` shows no `ok` for that move.

- [ ] **Step 6: Verify dry-run**

Complete Task 16 first (it guards execution in dry-run). Then open settings, toggle **Dry-run** on, and issue a move command with a real test file in Downloads.
Expected: no approval modal, no actual move; the chat shows a `[dry-run] would move …` message; the file stays put; `audit.log` records `"result": "dry-run"`.

- [ ] **Step 7: Write the README**

Create `README.md`:
```markdown
# AI Desktop Agent

A local Windows desktop agent that manages files via natural language. Runs entirely on your machine (Ollama + a local model).

## Prerequisites
- Windows 10/11 with WebView2 (ships by default on Win11).
- [uv](https://docs.astral.sh/uv/) for the Python backend.
- Node.js + npm for the frontend.
- [Ollama](https://ollama.com) running locally with a model pulled: `ollama pull qwen3.5:2b`.

## Run (development)
```bash
# frontend
cd frontend && npm install && npm run build
# backend
cd ../backend && uv sync && uv run python -m agent.main
```

## Test
```bash
cd backend && uv run pytest -v
```

## Current scope
Two tools: `list_dir` (read-only) and `move_file` (destructive, requires approval).
Safety: allowed-roots enforcement, per-tool-call approval, recycle-bin deletes (for future delete_file), audit log, dry-run.
```

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: README with run and test instructions"
```

---

### Task 16: Close the dry-run execution gap

**Files:**
- Modify: `backend/src/agent/tools.py` (guard execution in `move_file` when dry-run)
- Test: `backend/tests/test_safety.py` (add a dry-run execution test)

**Rationale:** Per the design's non-negotiable ("acting-for-real vs just-showing"), dry-run must prevent the *action*, not merely the *approval prompt*. Task 8's gate skips the interrupt in dry-run, so without this guard a dry-run move would execute unapproved. Fix at the trust boundary (the tool), matching the Global Constraint that guardrails live in tools.

**Interfaces:**
- Consumes: `agent.safety.dry_run`.
- Produces: `move_file` returns a dry-run preview string and performs no filesystem change when `dry_run()` is true.

- [ ] **Step 1: Write the failing test (append to test_safety.py)**

Add to `backend/tests/test_safety.py`:
```python
def test_move_file_dry_run_does_not_move(tmp_path, monkeypatch):
    from agent import tools
    root = tmp_path / "Downloads"
    root.mkdir()
    src = root / "a.txt"
    src.write_text("x")
    dst = root / "b.txt"
    monkeypatch.setattr("agent.tools.dry_run", lambda: True)
    monkeypatch.setattr("agent.safety.load_settings", lambda: type("S", (), {"allowed_roots": [str(root)], "dry_run": True})())
    result = tools.move_file.invoke({"src": str(src), "dst": str(dst)})
    assert "dry-run" in result.lower()
    assert src.exists() and not dst.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && uv run pytest tests/test_safety.py -k dry_run -v
```
Expected: FAIL — either `move_file` moves the file (assert fails) or `dry_run` import error.

- [ ] **Step 3: Add the guard to move_file**

Edit `backend/src/agent/tools.py` — add to the imports:
```python
from agent.safety import PathNotAllowed, audit, dry_run, resolve_and_check
```
And in `move_file`, immediately before `dst_p.parent.mkdir(...)`, insert:
```python
    if dry_run():
        audit({"tool": "move_file", "src": str(src_p), "dst": str(dst_p), "result": "dry-run"})
        return f"[dry-run] would move {src_p.name} to {dst_p}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd backend && uv run pytest -v
```
Expected: PASS (12 passed — 9 safety + 3 gate).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent/tools.py backend/tests/test_safety.py
git commit -m "fix: dry-run prevents move execution, not just approval"
```

---

## Notes for the implementer

- **Run everything through `uv`** from the `backend/` dir: `uv run pytest`, `uv run python -m agent.main`. Never `pip install`.
- **LangChain import drift:** if `GenericFakeChatModel` or `langchain_core.tools.tool` import paths differ in the resolved versions, confirm with a one-line `uv run python -c "import ..."` and adjust — the names are stable but module paths occasionally move between minor versions.
- **`astream_events` version:** the plan uses `version="v2"`. If the installed langgraph emits a deprecation pointing to `v3`, switch the string; event names (`on_tool_start`) are the same.
- **Git:** this repo isn't initialized yet. Before Task 1's first commit, run `git init` at the repo root and add a `.gitignore` (ignore `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`, `*.db`, `audit.log`).
