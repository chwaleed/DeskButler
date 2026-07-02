# DeskButler — Tool Catalog & Roadmap

Everything the agent should eventually be able to do, organized into phases.
This is a catalog, not an implementation plan. Today we ship Phase 0
(`list_dir`, `move_file`); each later phase is mostly "write more `@tool`
functions" — the runtime, safety gate, and UI already exist.

## Ground rules (why tools look the way they do)

These constraints come from running a 2B local model, and they shape every
tool below:

1. **Few, simple arguments.** ≤3 args, strings and booleans only. qwen3.5:2b
   emits garbage on nested/optional-heavy schemas. Complexity lives *inside*
   the tool, not in the model's reasoning.
2. **Every path through `resolve_allowed`.** Loose names tolerated
   ("my downloads"), escapes denied, allowed roots only. No exceptions —
   tools are the trust boundary, not the prompt.
3. **Destructive = approval + dry-run + reversible.** Anything that
   changes/removes data goes through the interrupt gate, honors dry-run, and
   prefers recoverable operations (recycle bin, fail-if-exists) over
   overwrites. Everything audits to `audit.log`.
4. **Capped output.** Every tool truncates like `list_dir` does (120 entries,
   `…N more`). A 16k context dies fast on raw file dumps.
5. **Bulk work = one tool call, one approval.** The model must never emit 50
   `move_file` calls for one request. Batch tools take a plan and execute it
   atomically-ish, reporting per-item results. This is the single most
   important design rule for "organize my folder".
6. **Tool-count budget.** A 2B model degrades noticeably past ~10–12 tools.
   As phases land: either recommend qwen3.5:4b as default, or add tool
   groups the user can toggle in settings (e.g. "developer tools off").

Legend: 🟢 read-only (no approval) · 🟡 creates things (approval only when
overwriting) · 🔴 destructive (always gated).

---

## Phase 0 — Shipped

| Tool | Args | Does | Risk |
|---|---|---|---|
| `list_dir` | `path` | List folder contents, capped at 120 entries | 🟢 |
| `move_file` | `src, dst` | Move/rename, fail-if-exists, forbidden-ext check | 🔴 |

## Phase 1 — Core file operations

The minimum set that makes "chat with my computer" feel real.

| Tool | Args | Does | Risk |
|---|---|---|---|
| `copy_file` | `src, dst` | Copy file or folder; fail if destination exists | 🟡 |
| `delete_file` | `path` | Send to Recycle Bin (send2trash) — never hard delete | 🔴 |
| `create_folder` | `path` | `mkdir -p`; no-op if it exists | 🟡 |
| `write_file` | `path, content, overwrite=false` | Create a text file ("create a shopping list on my Desktop") | 🟡 / 🔴 if overwrite |
| `read_file` | `path` | Return text content, capped ~10 KB; refuse binaries | 🟢 |
| `file_info` | `path` | Size, created/modified dates, type, hidden/readonly flags | 🟢 |

Notes:
- `rename_file` is deliberately absent — `move_file` already is rename. The
  system prompt should say so instead of adding a near-duplicate tool.
- For *editing* files with a 2B model, full rewrite (`read_file` →
  `write_file` with `overwrite=true`) is far more reliable than
  find-and-replace diffs. A dedicated `edit_file(path, find, replace)` can
  come later if rewrites prove too slow on big files.

## Phase 2 — Search & organize

The headline feature: "organize my Downloads — images to Pictures,
installers deleted, documents by year."

| Tool | Args | Does | Risk |
|---|---|---|---|
| `folder_stats` | `path` | Counts + total size grouped by extension/category; recursive | 🟢 |
| `search_files` | `folder, pattern` | Recursive glob on names (`*.pdf`, `report*`), capped | 🟢 |
| `search_content` | `folder, query` | Grep text files for a phrase, return path + matching line, capped | 🟢 |
| `batch_move` | `moves` (list of `{src, dst}`) | Execute a whole organize plan in one gated call; creates missing dest folders; per-item skip-and-report on failure | 🔴 one approval for the whole batch |
| `batch_delete` | `paths` | Recycle-bin many files in one gated call | 🔴 |
| `find_duplicates` | `folder` | Hash-based duplicate report (report only — deleting is the user's next command) | 🟢 |

How "organize by my format" actually executes:

```
user prompt (with the format rules)
  → folder_stats / list_dir        (model sees what's there)
  → model builds the plan          (pure reasoning, no tools)
  → batch_move(plan)               (ONE approval card listing all N moves)
  → summary reply
```

UI implication: the approval card must render a scrollable N-item plan
(blast radius view), not just a one-line description.

## Phase 3 — Content tools

Working *with* file contents, not just file names.

| Tool | Args | Does | Risk |
|---|---|---|---|
| `append_file` | `path, text` | Append to an existing text file (notes, logs, todo lists) | 🟡 |
| `read_pdf` | `path` | Extract text (pypdf), capped — enables "summarize this PDF" | 🟢 |
| `read_docx` | `path` | Extract text (python-docx), capped | 🟢 |
| `zip_create` | `src, dst` | Zip a folder/file (stdlib `shutil.make_archive`) | 🟡 |
| `zip_extract` | `archive, dst` | Extract into a new folder; refuse path-traversal entries | 🟡 |
| `convert_image` | `src, dst` | Format convert / resize via Pillow ("make this PNG a JPEG") | 🟡 |

Note: "summarize", "translate", "explain" are **not tools** — they're the
model reading `read_file`/`read_pdf` output. Don't build tools for what the
model already does.

## Phase 4 — Developer tools

"Init a Python project", "set up a React app", "what's the git status here".

| Tool | Args | Does | Risk |
|---|---|---|---|
| `init_project` | `kind, folder, name` | Templated scaffolds: `python`→`uv init`, `react`→`npm create vite`, `node`→`npm init -y`, `git`→`git init`. Fixed recipes, not free-form shell | 🔴 (creates many files) |
| `git_status` | `folder` | Porcelain status + current branch | 🟢 |
| `open_in_editor` | `path` | Launch VS Code (`code <path>`) | 🟢 |
| `run_command` | `command, cwd` | The escape hatch: allowlisted binaries only (`git`, `npm`, `uv`, `python`), always approval-gated, 60 s timeout, output capped | 🔴 always |

Notes:
- `init_project` as fixed recipes is the whole point — a 2B model given raw
  shell will invent flags. Recipes are testable; shell isn't.
- `run_command` ships **last** in this phase, and only with the allowlist.
  No `cmd /c`, no PowerShell strings, no pipes.

## Phase 5 — System & apps

The "butler" part: open things, tell me about my machine.

| Tool | Args | Does | Risk |
|---|---|---|---|
| `open_file` | `path` | `os.startfile` — open in default app | 🟢 |
| `show_in_explorer` | `path` | Reveal in Explorer, selected | 🟢 |
| `open_app` | `name` | Launch from a small known-apps registry (notepad, calculator, browser, terminal, vs code) — not arbitrary exe paths | 🟢 |
| `open_url` | `url` | Open in default browser | 🟡 approval (leaves the machine) |
| `system_info` | — | Free disk per drive, RAM, battery %, OS version | 🟢 |
| `clipboard_read` / `clipboard_write` | — / `text` | Read/set clipboard ("put that path on my clipboard") | 🟢 / 🟡 |
| `empty_recycle_bin` | — | Permanently purge — the one truly irreversible tool | 🔴 always |

## Phase 6 — Automation (features, not tools)

These are app capabilities the agent configures, not `@tool` functions the
model calls mid-chat:

- **Watch folders** — "whenever something lands in Downloads, apply my
  organize rules." A background watcher that replays a saved `batch_move`
  plan (with notification + undo, or queued approval).
- **Saved routines** — name a multi-step flow ("my weekly cleanup") and
  re-run it by name.
- **Scheduled runs** — routines on a timer.
- **Undo log** — because `batch_move` records every `src → dst`, an
  `undo_last` command is nearly free. Worth pulling forward if bulk
  organizes see real use.

## Explicitly out of scope

- **Web search / browsing** — breaks the "fully local, nothing leaves your
  computer" promise the UI makes. Revisit only as an explicit opt-in.
- **Email / calendar / messaging** — different product.
- **Registry edits, service control, killing processes, disk formatting,
  installing software** — no. The failure mode of a 2B model with these is
  a broken machine.
- **Arbitrary unsandboxed shell** — `run_command`'s allowlist is the
  ceiling, permanently.

## Suggested build order

1. **Phase 1 + `batch_move` + `folder_stats`** — this alone delivers the
   "organize my Downloads" demo, file creation, and reading. ~9 tools total;
   still inside the 2B comfort zone.
2. **Rest of Phase 2, then Phase 3** — search and content. Around here,
   evaluate 4b-by-default or tool groups in settings.
3. **Phase 4** — `init_project` first, `run_command` last.
4. **Phase 5** — cheap wins, sprinkle in anytime (each is ~20 lines).
5. **Phase 6** — only after bulk organize proves itself.

Every phase = new `@tool` functions in `tools.py` + a line in the system
prompt + tests in `test_safety.py`/`test_gate.py`. Nothing else changes.
