# Design: Project base + first 2 tools

**Date:** 2026-07-01
**Status:** Approved (design phase)
**Parent architecture:** [`docs/plan.md`](../../plan.md)

## Goal

Stand up the complete, permanent skeleton of the local desktop AI agent — the runtime spine, the safety layer, and a working end-to-end UI — while shipping only **two tools**: `list_dir` and `move_file`. Adding the remaining tools (`copy_file`, `delete_file`, `search_by_name`, `open_app`) later must be *pure tool-writing*: write the function, add its name to a set. No changes to the graph, bridge, UI, or safety plumbing.

The two tools are chosen to exercise every part of the base from day one:
- `list_dir` — the read-only path (falls straight through the safety gate).
- `move_file` — the destructive path (allowed-roots check, exe/DLL rejection, approval interrupt/resume, audit log).

If both tools work end-to-end, the entire base is validated.

## Scope decisions

| Decision | Choice | Rationale |
|---|---|---|
| Tools in base | `list_dir` + `move_file` | One read + one destructive → exercises the full safety spine |
| Safety spine | Built fully now | Later tools become pure tool-writing |
| UI | Full end-to-end thin slice | Window + chat + action log + approval modal + bridge, all wired |
| Persistence | `SqliteSaver` (on-disk, app-data) | History survives restarts; no migration later |
| Testing | Guardrails + gate only | Highest-data-loss code; skip UI and happy-path tests |
| Approval granularity | Per-tool-call | One AI message can carry multiple destructive calls; interrupt each individually |
| Event transport | `evaluate_js("window.onAgentEvent(...)")` fed by `astream_events`, keyed by turn id | Single global JS handler; pywebview-thread-safe |

## Architecture

Two processes: the app (pywebview window + Python backend + in-process tools, all one process) and Ollama (localhost HTTP). No MCP subprocess. Tools touch the same disk the backend sits on, so there is no process boundary between them.

```
┌──────────────────────────────┐
│   Desktop app (one process)  │
│  React UI ──js_api bridge──▶  │
│  Python backend               │
│   • runtime spine (worker loop, checkpointer, thread_id)
│   • LangGraph: call_model → safety_gate → tools
│   • tools.py (list_dir, move_file)
│   • safety.py (allowed-roots, recycle-bin, audit, dry-run)
└───────────────┬──────────────┘
                │ HTTP (localhost)
                ▼
        Ollama (qwen3.5)
```

### Backend components (`backend/`)

| File | Responsibility |
|---|---|
| `main.py` | Entry point: start the worker-thread asyncio loop, then `webview.create_window` + `webview.start()`. Runs the Ollama health check before showing the window. |
| `runtime.py` | The shared spine. One long-lived asyncio loop on a dedicated worker thread, started at launch. Graph compiled **once** with `SqliteSaver` + a fixed `thread_id`. Exposes `run_turn(turn_id, text)`, `resume_turn(decision)`, `cancel()` coroutines. All `Api` methods schedule onto this loop via `asyncio.run_coroutine_threadsafe`. Never `asyncio.run()` per message. |
| `agent.py` | Graph definition. Nodes: `call_model` (bound model, bound once), `safety_gate` (own node), `tools` (`ToolNode`). Edges: `START → call_model`; conditional `call_model → safety_gate | END`; `safety_gate → tools`; `tools → call_model`. |
| `tools.py` | The `@tool` functions. **Base = `list_dir` + `move_file` only.** Each function calls into `safety.py` for its guardrails — guardrails live *inside* the tool, which is the trust boundary. |
| `safety.py` | `resolve_and_check(path)` canonicalization + allowed-roots enforcement; `recycle_delete(path)` (built and tested now, used by `delete_file` later); `audit(entry)` JSON-lines writer; `is_destructive(name)` / the `DESTRUCTIVE` set; dry-run flag read. |
| `bridge.py` | The pywebview `Api` class: `send_message(text) -> turn_id`, `approve(decision)`, `cancel()`. Pushes streamed steps + final answer to the UI via `evaluate_js`. |
| `settings.py` | Load/save allowed-roots, model size, dry-run to a JSON file in the app-data dir. Read by the backend guardrails, not the UI. |
| `prompts.py` | System prompt. |
| `requirements.txt` | `langgraph`, `langchain`, `langchain-ollama` (or the init_chat_model provider pkg), `pywebview`, `send2trash`, `pytest`. |

### Frontend components (`frontend/src/`)

`App.tsx`, `ChatThread.tsx`, `ActionLog.tsx`, `ApprovalModal.tsx`, `SettingsPanel.tsx`, `api/bridge.ts` (wraps `window.pywebview.api` and registers `window.onAgentEvent`). All wired end-to-end; the base simply has two tools to drive them.

## The two tools

**`list_dir(path)`** — read-only.
- `safety.resolve_and_check(path)` → canonicalize (`Path(path).resolve()`), reject UNC/device prefixes, require `is_relative_to` an allowed root.
- Return directory entries.
- Not in `DESTRUCTIVE` → the gate lets it through with no interrupt.

**`move_file(src, dst)`** — destructive.
- Both paths `resolve_and_check`ed.
- Reject `dst` with an executable/DLL extension (`.exe .dll .bat .cmd .ps1 .scr .lnk`).
- Fail if `dst` exists unless the move was approved (gate on effect: a move onto an existing path clobbers bytes).
- In `DESTRUCTIVE` → the gate `interrupt()`s per call; on approve, execute the move; on reject, return a rejection `ToolMessage`.
- Every call (approved, rejected, executed, failed) → `safety.audit(...)`.

Note: `move_file` doesn't use the Recycle Bin, but `safety.recycle_delete` is built and unit-tested in the base so `delete_file` is a drop-in later.

## Data flow

1. User types → React calls `send_message(text)` → returns `turn_id` immediately, schedules `run_turn` on the worker loop.
2. `run_turn` invokes the graph with the fixed `thread_id` (so prior conversation state carries over) and streams events.
3. `call_model` → Ollama with history + tool schemas → tool call or final answer.
4. Tool call → `safety_gate`. Non-destructive → straight to `tools`. Destructive and not dry-run → `interrupt(request)`; graph suspends (state saved by `SqliteSaver`); backend pushes an approval request to the UI.
5. `approve(decision)` / reject → resume via `Command(resume=decision)` on the same `thread_id`. Approved executes; rejected short-circuits.
6. Each step streamed to the action log via `onAgentEvent`; loop returns to step 3 until a final text answer.
7. Final answer pushed to the UI, keyed by `turn_id`.

## Error handling

All errors surface as a chat bubble or a blocking UI state — never a crash.

- **Ollama down / model not pulled** — startup health check against `/api/tags` (daemon up + model present). If either fails, show a blocking, actionable UI state before the window is usable.
- **Tool error** (path outside roots, dst exists, move failed) — returned as an error `ToolMessage` the model sees, and written to the audit log.
- **`model.invoke` failure** — try/except → chat bubble.
- **Cancellation** — a `threading.Event` checked between graph steps; Stop button → `api.cancel()`.
- **Concurrency** — a second `send_message` while one is in flight is rejected with a busy signal; the input box is disabled until the turn completes.

## Testing (guardrails + gate only)

`pytest`, no additional framework. The base's highest-data-loss code gets tests; UI and happy paths do not.

- **`test_safety.py`** — `resolve_and_check`: inside/outside allowed roots, `..` traversal, symlink/junction, case-insensitivity (`c:\windows`), 8.3 short names, UNC/`\\?\` rejection. Plus `recycle_delete` sends to the Recycle Bin.
- **`test_gate.py`** — the interrupt/resume flow: a destructive call pauses; approve executes; reject short-circuits with a rejection message; a mixed message (safe + destructive tool calls) handles partial approval correctly.

## Out of scope for the base (deferred)

- Tools `copy_file`, `delete_file`, `search_by_name`, `open_app` — add later as pure tool-writing.
- Semantic/content search.
- PyInstaller packaging + WebView2 bootstrapper + first-run `ollama pull` flow.
- Blast-radius file-count confirmation in the approval modal (single-file moves only in the base).
- Migration to PyTauri.

## Success criteria

The base is complete when, on real target hardware:
1. A user can type "list my Downloads" and see the result stream into the action log.
2. A user can type "move report.pdf to Documents", get an approval modal, approve it, and the file moves — with the whole exchange in the audit log.
3. Rejecting the approval leaves the file untouched and tells the model it was rejected.
4. `test_safety.py` and `test_gate.py` pass.
5. Adding a hypothetical third tool requires editing only `tools.py` (and its name in the `DESTRUCTIVE` set if destructive).
