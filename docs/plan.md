# Local desktop AI agent — architecture & build plan

## Overview

A Windows desktop application that lets you manage your computer in natural language — moving and organizing files, searching for them, launching applications — entirely on local hardware. A React/TypeScript UI runs inside a native window; a Python backend runs the agent logic on LangGraph. The agent's tools (filesystem operations, app launching) are plain in-process Python functions. The model is Ollama running qwen3.5, starting at 2B with a defined fallback path if it can't hold up under multi-step tool calling.

Nothing here needs network access — Ollama and the backend talk over localhost only.

## Tech stack at a glance

| Layer | Technology | Why |
|---|---|---|
| UI shell | pywebview | Wraps Windows' built-in WebView2 — no bundled Chromium, small footprint, simple Python↔JS bridge |
| Frontend | React + TypeScript (Vite) | Reuses your existing skillset; fastest path to a polished chat-style UI |
| Backend | Python 3.11+ | Agent logic, tool execution, filesystem/process access |
| Agent framework | LangGraph | Stateful graph, checkpointing, `interrupt()` for human-in-the-loop, conditional tool-calling loop |
| Tools | In-process `@tool` functions | Same process as the agent; no IPC, no subprocess, no packaging headache. (Reusability path: wrap the *same* functions in an MCP shim later, if an external client ever actually needs them. See "Open decisions".) |
| Model | Ollama — `qwen3.5:2b`, fallback `qwen3.5:4b`/`qwen3.5:9b` | Local inference, native tool calling, 256K context |
| Packaging | PyInstaller | Bundles backend + frontend build into one distributable `.exe` |

## High-level architecture

```
┌──────────────────────────────┐
│   Desktop app (one process)  │
│  ┌─────────────────────────┐ │
│  │  React + TypeScript UI  │ │
│  │  chat, action log       │ │
│  └────────────┬────────────┘ │
│               │ pywebview js_api bridge
│  ┌────────────▼────────────┐ │
│  │  Python backend          │ │
│  │  LangGraph agent         │ │
│  │  + safety gate node      │ │
│  │  + tool functions        │ │
│  └────────────┬────────────┘ │
└───────────────┼──────────────┘
                 │ HTTP (localhost)
                 ▼
        ┌──────────────────┐
        │  Ollama (local)   │
        │  qwen3.5          │
        └──────────────────┘
```

Two processes: the app (window + backend + tools, all one Python process) and Ollama. The window owns presentation, the backend owns decision-making and state, the model owns reasoning. Tools run in-process — they touch the same disk the backend sits on, so there's no reason to put a process boundary between them.

## The runtime spine (specify this first — everything depends on it)

Three of the app's features — the approval gate, memory across turns, and the streaming action log — are not separate problems. They share one mechanism, and it must be built before Phase 2's acceptance test can pass. Get this right first:

- **One long-lived asyncio loop on a dedicated worker thread**, started at app launch. The LangGraph graph is compiled **once** on it with a checkpointer and a fixed `thread_id`. `webview.start()` owns the main thread, so nothing agent-related runs there.
- Every `Api` method hands work to that loop via `asyncio.run_coroutine_threadsafe(coro, loop)`. **Never `asyncio.run()` per message** — a fresh loop each turn discards the checkpointer state and makes it impossible to hold an `interrupt()` open across a later `approve()` call.
- **Checkpointer + `thread_id`** give you two things at once: conversation memory across turns ("move them into that folder" resolves), and the ability to pause mid-run and resume. Use `MemorySaver` (in-process, zero deps) unless you want history to survive restarts, in which case `SqliteSaver` to a file in app-data.
- **The safety gate is its own graph node**, not something wedged "between `tools_condition` and `ToolNode`." `call_model` routes to the gate; the gate inspects each requested tool call, and for destructive ones calls `interrupt(request)` to pause. A separate `api.approve(decision)` resumes via `graph.invoke(Command(resume=decision), config)` on the same `thread_id`. Non-destructive calls fall straight through to the tools.
- **Streaming** uses the same loop: iterate `graph.astream_events(...)` and push each step to the UI with `window.evaluate_js("window.onAgentEvent(%s)" % json.dumps(event))`. `evaluate_js` is safe to call from the worker thread.

## Components

### Frontend — native window + React/TypeScript UI

The window hosts a built React app (Vite output, static files) inside pywebview. Four surfaces: a chat thread for commands and responses; a live action log fed by `window.onAgentEvent(...)` events ("listing Downloads…", "moving 12 files…"); an approval modal that appears when the backend interrupts on a destructive call; and a settings panel (model size, allowed root directories, dry-run toggle).

Communication goes through pywebview's `js_api` bridge — simpler than a separate HTTP server for a single-user desktop app, no port to configure. **`js_api` methods already run on their own thread** (pywebview guarantees this), so they don't block the UI, but they must still hand the actual agent work to the shared loop rather than running it inline:

```python
class Api:
    def send_message(self, text: str) -> str:
        # fire-and-forget: schedule on the shared loop, return an ack immediately.
        # the answer + action-log steps arrive via window.onAgentEvent(...).
        turn_id = new_turn_id()
        asyncio.run_coroutine_threadsafe(run_turn(turn_id, text), loop)
        return turn_id

    def approve(self, decision: dict) -> None:
        asyncio.run_coroutine_threadsafe(resume_turn(decision), loop)

    def cancel(self) -> None:
        cancel_event.set()   # checked between graph steps
```

```typescript
const turnId = await window.pywebview.api.send_message(userText)
// results stream in via window.onAgentEvent(event), keyed by turnId
```

`send_message` returns a turn id, not the answer — a full agent turn can take many seconds and the UI shouldn't block on it. Reject or queue a second message while one is in flight (a busy flag; disable the input box).

### Backend — Python agent core

A single LangGraph graph: a model node, a safety-gate node, and a tool node, looping until the model stops requesting tools.

```python
# illustrative — see "runtime spine" for loop/thread/checkpointer setup
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain.chat_models import init_chat_model
from tools import TOOLS  # plain @tool functions, defined in-process

model = init_chat_model("ollama:qwen3.5:2b")  # bump to 4b/9b if Phase 0 fails
bound = model.bind_tools(TOOLS)               # bind once, not per call

DESTRUCTIVE = {"move_file", "delete_file", "copy_file"}

def call_model(state: MessagesState):
    return {"messages": [bound.invoke(state["messages"])]}

def safety_gate(state: MessagesState):
    # inspect the last AI message's tool_calls; pause on any destructive one.
    last = state["messages"][-1]
    for call in last.tool_calls:
        if call["name"] in DESTRUCTIVE and not dry_run:
            decision = interrupt({"tool": call["name"], "args": call["args"]})
            if decision == "reject":
                # short-circuit: hand back a rejection ToolMessage, don't execute
                ...
    return state

def route(state: MessagesState):
    return "safety_gate" if state["messages"][-1].tool_calls else END

graph = StateGraph(MessagesState)
graph.add_node(call_model)
graph.add_node(safety_gate)
graph.add_node("tools", ToolNode(TOOLS))
graph.add_edge(START, "call_model")
graph.add_conditional_edges("call_model", route, {"safety_gate": "safety_gate", END: END})
graph.add_edge("safety_gate", "tools")
graph.add_edge("tools", "call_model")

app = graph.compile(checkpointer=MemorySaver())  # thread_id supplied per invoke
```

Keep the tool count lean — five or six well-named tools (`list_dir`, `move_file`, `copy_file`, `delete_file`, `search_by_name`, `open_app`) beat twenty granular ones. The reason is **decision reliability**, not token cost: fewer options means fewer wrong picks for a small model.

The guardrails (allowed-roots check, dry-run, delete-to-recycle-bin) live **inside the tool functions themselves**, not only in the graph node. The tool is the trust boundary. This also means the guardrails hold even if a tool is ever called from somewhere other than this graph.

### Model layer — Ollama

Ollama serves `qwen3.5:2b` over its native tool-calling API. Two things to settle in Phase 0, on your real target hardware:

- **Thinking mode on or off.** qwen3.5 is thinking-capable; on a CPU-only or GPU-poor box, thinking tokens across a multi-iteration loop can make the UI feel frozen. Measure tokens/sec and per-turn wall-clock; set a latency ceiling.
- **First-run readiness.** On a fresh machine the daemon may be down or `qwen3.5:2b` never pulled — the most likely failure of all. A startup health check hits Ollama's `/api/tags` (daemon up + model present) and shows a blocking, actionable UI state if either is missing. Wrap `model.invoke` in try/except and surface errors as a chat bubble rather than a crash.

## Request lifecycle

1. User types a command; React calls `send_message(text)`, gets back a turn id.
2. The backend schedules the turn on the shared loop with the fixed `thread_id`, so the graph resumes from prior conversation state.
3. The model node calls Ollama with message history + tool schemas.
4. The model returns a tool call or a final answer.
5. Tool call → the safety-gate node inspects it. Non-destructive → straight to tools. Destructive and not dry-run → `interrupt()`; the backend pushes an approval request to the UI and the graph suspends (state saved by the checkpointer).
6. On `approve()`/`reject()`, the graph resumes via `Command(resume=...)`; approved calls execute, rejected calls get a rejection message.
7. Each step is streamed to the action log via `window.onAgentEvent(...)`; the loop returns to step 3 until a final text answer.
8. The final answer is pushed to the UI, keyed by turn id.

## Safety & guardrails

A small model misjudges arguments more than a large one, so guardrails matter more here. All of these are enforced **inside the tool functions**:

- **Default-deny on `move_file`, `delete_file`, and `copy_file`** without explicit approval. Gate on *effect*, not name — a copy or move onto an existing path clobbers bytes, so treat that as destructive too. Default all three to fail-if-destination-exists unless approved.
- **Deletes go to the Recycle Bin** (`send2trash` — a tiny dependency), never `os.remove`. A rubber-stamped bad delete becomes a one-click restore instead of permanent loss.
- **Allowed-roots as a canonicalized check.** Resolve the argument with `Path(arg).resolve()`, reject UNC/device prefixes (`\\?\`, `\\server\`), and compare with `is_relative_to(root)`. A naive string-prefix check is bypassed by `..`, junctions/symlinks, case (`c:\windows`), and 8.3 short names. Keep a configurable allow-list (Downloads, Documents — never `C:\Windows` or `Program Files`). Re-validate the path inside the tool at execution time, not only at approval time.
- **`open_app` maps an app name → a fixed absolute exe path**, launched via `subprocess` with a list argv and no `shell=True`. Pass **no** model-controlled arguments (or only per-app schema-validated ones) — otherwise allowlisted apps like `cmd.exe` or a browser become universal launchers that bypass every file guardrail.
- **Reject executable/DLL extensions** (`.exe .dll .bat .cmd .ps1 .scr .lnk`) as destinations for any move/copy/delete. Otherwise the agent can plant a hostile `version.dll` next to a trusted exe and `open_app` side-loads it via Windows' DLL search order.
- **Audit log** of every tool call (args + result) to a JSON-lines file in the app-data dir — not in a directory the agent's own tools can reach.
- **Dry-run mode** shows what the agent would do without doing it. Enforced in the tool functions, so a flipped setting or a graph-node bug can't silently arm real destruction.
- **Blast-radius confirmation:** for bulk operations, expand the concrete file list + count into the approval modal, and re-confirm above a threshold (e.g. >20 files).

## Project structure

```
ai-desktop-agent/
├── backend/
│   ├── agent.py          # graph definition + shared loop / thread setup
│   ├── tools.py          # @tool functions with guardrails baked in
│   ├── safety.py         # allowed-roots resolve/check, recycle-bin delete, audit log
│   ├── prompts.py
│   ├── main.py           # entry point — starts pywebview window + worker loop
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatThread.tsx
│   │   │   ├── ActionLog.tsx
│   │   │   ├── ApprovalModal.tsx
│   │   │   └── SettingsPanel.tsx
│   │   ├── api/bridge.ts  # wraps window.pywebview.api + onAgentEvent
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

Flat backend on purpose — split a file only when it gets uncomfortable, not before.

## Build phases

**Phase 0 — model validation.** No LangGraph, no UI. A plain script hitting Ollama directly with two or three tool definitions, running the "list Downloads, then move every PDF into Documents/PDFs" task. **Define "reliably" concretely:** run it 20× at temperature 0, require ≥18/20 fully correct with zero destructive-argument errors and valid tool-call JSON every time; log the failure category for the rest. Reuse the same script across 2b/4b/9b. This gates everything — if `qwen3.5:2b` fails, swap to `4b`/`9b` now, before any architecture is built on it. Also settle thinking-mode and measure per-turn latency here.

**Phase 1 — backend core.** The shared loop + thread, the compiled graph with checkpointer, the in-process tools, running headless from the CLI. Confirm the agent reliably calls the right tools with the right arguments and that conversation state carries across turns.

**Phase 2 — safety layer.** Allowed-roots (canonicalized), the `interrupt()`-based approval gate, recycle-bin deletes, and the audit log, still CLI-driven. **Acceptance test:** a destructive call actually pauses, waits for a separate approve/reject, and resumes correctly — including a message carrying multiple tool calls where only some are destructive. Unit-test the path-containment check (inside/outside roots, `..`, symlinks, case, 8.3, UNC), the `open_app` allowlist, and the dry-run short-circuit — this is the highest-data-loss code in the app.

**Phase 3 — minimal UI.** pywebview window, bare-bones React chat box, the bridge and `onAgentEvent` wired end to end, including the approval modal round trip. One full turn working before building out the rest.

**Phase 4 — polish.** Action-log visualization, settings panel + persistence, dry-run toggle, cancellation (Stop button → `api.cancel()`), packaging.

## Packaging & distribution

PyInstaller bundles the Python backend and pywebview shell into a single `.exe`; the React build ships alongside as static files loaded by the window. Because tools are in-process there's no subprocess to launch and no `python`-on-PATH problem — resolve any bundled asset paths via `sys._MEIPASS`, never `./`. WebView2 ships with Windows 11 and most current Windows 10 installs; bundle the WebView2 bootstrapper as a fallback installer step for machines that lack it. If distributing to others, add a first-run `ollama pull` flow with progress (the model is multiple GB).

## Open decisions to revisit

- Whether `qwen3.5:2b` survives Phase 0 or needs `4b`/`9b`.
- Whether `SqliteSaver` (history survives restarts) is worth it over `MemorySaver`.
- Whether "search for any file" needs to grow beyond filename matching into content/semantic search — if so, that's one additional tool backed by a local embedding index, not a rearchitecture.
- Whether to expose the tools as an MCP server for external clients (Goose/Claude Desktop). If that need ever becomes real, wrap the *existing* `tools.py` functions in an MCP shim — a thin second entry point, not a rewrite. Deliberately deferred until an actual external client exists.
- Whether pywebview stays the shell long-term or gets swapped for PyTauri once that binding matures.
