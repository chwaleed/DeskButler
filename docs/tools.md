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

## Phase 0 + build-step 1 — Shipped

Shipped and unit-tested (50 backend tests). Work end to end with the real
qwen3.5:2b model, including multi-file moves via the grouped approval gate.

| Tool | Args | Does | Risk |
|---|---|---|---|
| `list_dir` | `path` | List folder contents, capped at 120 entries | 🟢 |
| `read_file` | `path` | Return text content, capped ~10 KB; refuse binaries | 🟢 |
| `file_info` | `path` | Size, created/modified dates, type, hidden flag | 🟢 |
| `folder_stats` | `path` | Counts + total size grouped by extension, recursive, walk-capped | 🟢 |
| `create_folder` | `path` | `mkdir -p`; no-op if it exists | 🟡 |
| `write_file` | `path, content, overwrite=false` | Create a text file | 🟡 / 🔴 if overwrite |
| `copy_file` | `src, dst` | Copy file or folder; fail if destination exists | 🟡 |
| `move_file` | `src, dst` | Move/rename, fail-if-exists, forbidden-ext check | 🔴 |
| `delete_file` | `path` | Send to Recycle Bin — never hard delete; refuses allowed-root itself | 🔴 |
| `batch_move` | `moves` (list of `{src, dst}`) | Whole organize plan in ONE gated call; per-item skip-and-report; capped at 200 | 🔴 |

**Grouped approval gate:** the 2B model often emits several `move_file` calls
in one message instead of a single `batch_move`. The safety gate collects all
destructive calls in a message and shows ONE approval listing every action;
one Approve runs them all, one Reject cancels them all (and answers every
tool_call so the model can continue). This is what makes multi-file moves
work regardless of whether the model chose `batch_move` or repeated
`move_file`.

## Phase 1 — remaining core file operations

None — all Phase 1 tools shipped above.

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

`folder_stats` and `batch_move` already shipped (see build-step 1 above).
Remaining:

| Tool | Args | Does | Risk |
|---|---|---|---|
| `search_files` | `folder, pattern` | Recursive glob on names (`*.pdf`, `report*`), capped | 🟢 |
| `search_content` | `folder, query` | Grep text files for a phrase, return path + matching line, capped | 🟢 |
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
| `convert_image` | `src, dst` | Format convert via Pillow ("make this PNG a JPEG") | 🟡 |
| `resize_image` | `src, dst, max_size` | Scale down to fit `max_size` px, keep aspect ratio | 🟡 |
| `compress_image` | `src, dst, quality` | Re-encode at lower quality ("shrink this to email it") | 🟡 |
| `image_info` | `path` | Dimensions, format, DPI, EXIF summary (camera, GPS present?) | 🟢 |

Note: "summarize", "translate", "explain" are **not tools** — they're the
model reading `read_file`/`read_pdf` output. Don't build tools for what the
model already does. Same for unit conversion, text case changes, word counts
of pasted text — pure reasoning, zero tools.

## Phase 4 — Local utilities (skip the website)

Everyday jobs people paste files into random websites for. Doing them
locally is exactly DeskButler's pitch: your files never leave the machine.
Almost all of these ride on deps we'd already have (Pillow, pypdf) or the
stdlib.

| Tool | Args | Does | Risk |
|---|---|---|---|
| `merge_pdf` | `paths, dst` | Combine PDFs into one (pypdf) | 🟡 |
| `split_pdf` | `src, pages, dst` | Extract a page range ("pages 2–5 as a new file") | 🟡 |
| `images_to_pdf` | `paths, dst` | Photos/scans → one PDF (Pillow) | 🟡 |
| `pdf_to_images` | `src, dst_folder` | Render pages as PNGs (pypdfium2) | 🟡 |
| `strip_metadata` | `src, dst` | Copy image/PDF minus EXIF/GPS/author — the privacy tool | 🟡 |
| `file_hash` | `path, algo=sha256` | Checksum for verifying downloads (stdlib hashlib) | 🟢 |
| `qr_code` | `text, dst` | Generate a QR code PNG (`qrcode` lib, tiny) | 🟡 |
| `generate_password` | `length=20` | Cryptographically random password (stdlib `secrets`) — never let the model invent one | 🟢 |
| `ocr_image` | `path` | Image → text via Tesseract, capped — enables "read this screenshot" | 🟢 |
| `media_convert` | `src, dst` | Audio/video conversion + audio extraction via ffmpeg ("mp4 → mp3") | 🟡 |
| `media_info` | `path` | Duration, resolution, codec, bitrate (ffprobe) | 🟢 |

Notes:
- `ocr_image` and `media_convert`/`media_info` need external binaries
  (Tesseract, ffmpeg). The tool checks for them and returns "not installed —
  install X to enable this" instead of failing cryptically. They register
  only when found, so they don't eat tool-count budget on machines without
  them.
- `generate_password` exists because an LLM sampling "random" characters is
  not random. Determinism boundary: randomness comes from `secrets`, never
  the model.
- Compress-PDF is deliberately absent — real PDF compression is a rabbit
  hole (ghostscript). `strip_metadata` + re-save covers the common case;
  revisit if users actually ask.

## Phase 5 — Developer tools

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

## Phase 6 — System & apps

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

## Phase 7 — Process & network control (task manager)

Developer-grade control over the machine: "what's hogging port 3000, kill
it", "what's eating my RAM", "start the dev server". All of it rides on
`psutil` (one dependency covers processes, ports, and network).

| Tool | Args | Does | Risk |
|---|---|---|---|
| `list_processes` | `sort_by=memory` | Top ~25 by memory/CPU: name, PID, mem, CPU% | 🟢 |
| `process_info` | `name_or_pid` | Details for one process: path, started, mem, CPU, open ports | 🟢 |
| `check_port` | `port` | What's listening on it — process name + PID, or "free" | 🟢 |
| `kill_process` | `name_or_pid` | Terminate (graceful, then force after timeout) | 🔴 |
| `kill_port` | `port` | `check_port` + kill in one step — the "port 3000 is stuck" fix | 🔴 |
| `run_app` | `path, args` | Launch any exe with arguments, detached — beyond the Phase 6 registry | 🔴 |
| `list_services` | `filter` | Windows services: name, status, startup type (capped) | 🟢 |
| `service_control` | `name, action` | start / stop / restart a service | 🔴 |
| `network_info` | — | Local IPs, adapters, gateway, active connection count | 🟢 |
| `env_var` | `name` | Read an environment variable ("what's my JAVA_HOME?") | 🟢 |
| `startup_apps` | — | List programs that launch at boot (read-only) | 🟢 |
| `lock_screen` | — | Lock the workstation | 🟢 |
| `power_action` | `action` | sleep / restart / shutdown | 🔴 |

Notes:
- **Protected-process denylist** inside `kill_process`/`kill_port`: refuse
  system-critical processes (`csrss`, `wininit`, `winlogon`, `lsass`,
  `services`, `svchost`, PID ≤ 4), refuse anything in DeskButler's own
  process tree, and refuse `ollama` — killing the model mid-conversation is
  a self-lobotomy the agent shouldn't be able to perform.
- `kill_process` on an ambiguous name (3 × `node.exe`) must not guess: it
  returns the matching list and asks the user to pick a PID. Same
  determinism rule as paths — the tool disambiguates, never the model.
- `run_app` is gated because "run any exe" is exactly what malware wants.
  The approval card shows the full path + args. Forbidden: anything inside
  Windows/system directories.
- `service_control` and `power_action` need elevation for some targets —
  return the clear error, never attempt UAC bypasses.
- Setting env vars, editing startup entries: both are registry writes —
  still out of scope. Read-only is the line.

## Explicitly out of scope

- **Web search / browsing** — breaks the "fully local, nothing leaves your
  computer" promise the UI makes. Revisit only as an explicit opt-in.
- **Email / calendar / messaging** — different product.
- **Registry edits, disk formatting, installing/uninstalling software,
  UAC/elevation tricks** — no. The failure mode of a small model with these
  is a broken machine. (Process/service control moved *in* scope — Phase 7 —
  because it's gated, denylisted, and recoverable with a reboot. Registry
  and disk damage are not.)
- **Arbitrary unsandboxed shell** — `run_command`'s allowlist is the
  ceiling, permanently.

## Suggested build order

1. **Phase 1 + `batch_move` + `folder_stats`** — this alone delivers the
   "organize my Downloads" demo, file creation, and reading. ~9 tools total;
   still inside the 2B comfort zone.
2. **Rest of Phase 2, then Phase 3** — search and content. Around here,
   evaluate 4b-by-default or tool groups in settings.
3. **Phase 4** — local utilities. Independent of each other; pick by demand.
   By now tool groups in settings are mandatory, not optional — this phase
   alone is ~11 tools.
4. **Phase 5** — `init_project` first, `run_command` last.
5. **Phase 6** — cheap wins, sprinkle in anytime (each is ~20 lines).
6. **Phase 7** — read-only half first (`check_port`, `list_processes`,
   `network_info` — zero risk, instant developer value), kill/run/service
   control after the approval UX has proven itself on file operations.

Every phase = new `@tool` functions in `tools.py` + a line in the system
prompt + tests in `test_safety.py`/`test_gate.py`. Nothing else changes.
