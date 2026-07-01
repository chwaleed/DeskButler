# AI Desktop Agent

A local Windows desktop agent that manages files via natural language. Runs entirely on your machine (Ollama + a local model). A React UI runs inside a native window (pywebview); a Python backend runs a LangGraph agent whose tools are in-process functions.

## Prerequisites

- Windows 10/11 with WebView2 (ships by default on Win11; most current Win10).
- [uv](https://docs.astral.sh/uv/) for the Python backend.
- Node.js + npm for the frontend.
- [Ollama](https://ollama.com) running locally with a model pulled: `ollama pull qwen3.5:2b`.

## Run (development)

```bash
# frontend — build the static assets the window loads
cd frontend && npm install && npm run build

# backend — sync deps and launch the window
cd ../backend && uv sync && uv run python -m agent.main
```

## Test

```bash
cd backend && uv run pytest -v
```

Tests cover the highest-data-loss code: allowed-roots canonicalization (`..`, symlinks,
case, 8.3, UNC/device rejection), recycle-bin delete, the audit log, the dry-run guard,
and the approval interrupt/resume gate.

## Current scope

Two tools: `list_dir` (read-only) and `move_file` (destructive, requires approval).

Safety: allowed-roots enforcement inside the tool functions (the trust boundary),
per-tool-call approval via LangGraph `interrupt()`, recycle-bin deletes (wired for the
future `delete_file` tool), a JSON-lines audit log in `%LOCALAPPDATA%\ai-desktop-agent`,
and a dry-run mode that prevents execution (not just the approval prompt).

Adding more tools (`copy_file`, `delete_file`, `search_by_name`, `open_app`) is pure
tool-writing: add the function to `backend/src/agent/tools.py` and, if destructive, add
its name to the `DESTRUCTIVE` set in `backend/src/agent/safety.py`.
