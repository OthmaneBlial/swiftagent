# SwiftAgent — Progress & Handoff Document

> **Last updated:** 2026-03-02
> **Status:** WORK IN PROGRESS — multiple bugs, missing features
> **Original source:** Converted from the `base/accomplish` Electron monorepo

---

## Table of Contents

1. [What SwiftAgent Should Be](#what-swiftagent-should-be)
2. [Project Structure](#project-structure)
3. [What Has Been Built](#what-has-been-built)
4. [What Is Broken (Known Bugs)](#what-is-broken-known-bugs)
5. [What Is Completely Missing](#what-is-completely-missing)
6. [File-by-File Reference](#file-by-file-reference)
7. [How the Engine Works (and Why It's Wrong)](#how-the-engine-works-and-why-its-wrong)
8. [Git History](#git-history)
9. [How to Run](#how-to-run)
10. [Recommendations for the Next Developer](#recommendations-for-the-next-developer)

---

## What SwiftAgent Should Be

SwiftAgent is an **AI task automation tool** that lets users describe tasks in plain English and have an AI agent execute them. It should support:

| Feature | Description |
|---|---|
| 📁 **File Management** | Sort, rename, move, create, delete files based on user instructions |
| ✍️ **Document Writing** | Write, summarize, rewrite documents on demand |
| 🔗 **Tool Connections** | Work with Notion, Google Drive, Dropbox, local APIs |
| ⚙️ **Custom Skills** | Define repeatable workflows, save them as reusable skills |
| 🛡️ **Full Control** | User approves every action, can see logs, can stop at any time |
| 💬 **Interactive Chat** | Back-and-forth conversation with the agent, not just one-shot |

**The user's PC must be safe.** All agent work happens inside `~/.swiftagent/workspace`. The agent cannot touch files outside that sandbox.

### Supported LLM Providers (7 total)

| Provider | ID | Key Env Var | Status |
|---|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` | ✅ Configured in models |
| xAI (Grok) | `xai` | `XAI_API_KEY` | ✅ Configured in models |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | ✅ Configured in models |
| Google Gemini | `gemini` | `GEMINI_API_KEY` | ✅ Configured in models |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | ✅ Configured in models |
| Z-AI (GLM) | `zai` | `ZAI_API_KEY` | ✅ Configured in models |
| Ollama | `ollama` | *(none, local)* | ✅ Configured in models |

---

## Project Structure

```
swiftagent/
├── server/                          # Python backend (FastAPI)
│   ├── pyproject.toml               # Python project config
│   ├── requirements.txt             # Dependencies
│   └── swiftagent/
│       ├── main.py                  # FastAPI app entry point, lifespan
│       ├── cli.py                   # `onboard` CLI wizard
│       ├── config.py                # .env file parser, env key auto-import
│       ├── api/
│       │   ├── routes.py            # REST endpoints (tasks, settings, providers, keys)
│       │   └── websocket.py         # WebSocket handler + ConnectionManager
│       ├── engine/
│       │   ├── adapter.py           # OpenCode CLI subprocess adapter (⚠️ BUGGY)
│       │   ├── manager.py           # Task lifecycle orchestrator
│       │   └── parser.py            # NDJSON stream parser
│       ├── models/
│       │   ├── events.py            # WebSocket event types (WSEventType enum)
│       │   ├── provider.py          # Provider models, default models, labels, env vars
│       │   ├── settings.py          # AppSettings model
│       │   └── task.py              # Task, TaskConfig, TaskMessage, TaskResult models
│       ├── storage/
│       │   ├── database.py          # SQLite init/close with WAL mode + migrations
│       │   ├── secure.py            # AES-256-GCM encrypted API key storage
│       │   ├── tasks.py             # Task CRUD repository
│       │   ├── settings.py          # App settings repository
│       │   └── providers.py         # Provider settings repository
│       └── tools/
│           └── __init__.py          # Empty — MCP tools NOT implemented
├── client/                          # React frontend (Vite + TypeScript)
│   ├── package.json
│   ├── tailwind.config.js           # Tailwind with shadcn/ui theming
│   ├── postcss.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx                 # React entry point
│       ├── App.tsx                  # Root component, connects WebSocket
│       ├── router.tsx               # React Router (3 routes)
│       ├── components/
│       │   └── layout/Layout.tsx    # Sidebar nav (Tasks, History, Settings)
│       ├── lib/
│       │   ├── swiftagent.ts        # API client (REST + WebSocket)
│       │   └── utils.ts             # cn() helper for Tailwind
│       └── pages/
│           ├── Home.tsx             # Task launcher (input + send)
│           ├── Execution.tsx        # Task execution view (⚠️ BUGGY)
│           └── History.tsx          # Task history list
├── .env.example                     # Environment config template
├── .env                             # User's actual config (created by `make onboard`)
├── Makefile                         # Dev, install, onboard, clean commands
├── LICENSE                          # MIT
└── README.md                        # Documentation
```

---

## What Has Been Built

### ✅ Working

| Component | Details |
|---|---|
| **Python backend** | FastAPI app with CORS, lifespan, health check |
| **REST API** | Full CRUD for tasks, settings, providers, API keys |
| **WebSocket** | Bidirectional real-time events with typed messages |
| **SQLite database** | stdlib `sqlite3` with WAL mode, migrations |
| **Encrypted key storage** | AES-256-GCM via `cryptography` lib |
| **7 LLM providers** | Models, labels, env vars, catalog endpoint |
| **`.env` config** | Stdlib parser (no python-dotenv), auto-import keys |
| **Onboard CLI** | `make onboard` interactive wizard, `make onboard-show` status |
| **React frontend** | Vite + TypeScript + Tailwind + React Router |
| **Home page** | Task launcher with animated input |
| **History page** | Task list with delete and clear |
| **API client** | `swiftagent.ts` — fetch-based REST + WebSocket with auto-reconnect |
| **Workspace sandbox** | All tasks run inside `~/.swiftagent/workspace` |

### ⚠️ Partially Working

| Component | Issue |
|---|---|
| **Execution page** | Agent responds but then gets stuck in "Agent is responding..." infinite loop |
| **OpenCode adapter** | Uses `opencode run` correctly now, but exit/completion handling is broken |
| **Session resumption** | WebSocket event wired up but never tested end-to-end |

---

## What Is Broken (Known Bugs)

### 🔴 BUG 1: Infinite "Agent is responding..." loop (CRITICAL)

**File:** `client/src/pages/Execution.tsx`
**What happens:** After the agent sends its response, the UI shows a permanent "Agent is responding..." typing indicator that never goes away. The spinner stays forever.
**Root cause:** The `task:complete` event is either:
- (a) Never emitted by the adapter because `_handle_exit()` isn't triggered properly, OR
- (b) The process exit code isn't being detected because `opencode run` may not cleanly exit, OR
- (c) The `isRunning` check in the component remains `true` even after the opencode process ends

**Where to investigate:**
1. `server/swiftagent/engine/adapter.py` → `_read_stdout()` and `_handle_exit()` — does `_handle_exit` get called? Does the process actually exit?
2. `server/swiftagent/engine/adapter.py` → `_complete_task()` — does it broadcast `task:complete`?
3. `server/swiftagent/engine/manager.py` → `_run_adapter()` — does `adapter._process.wait()` ever return?
4. `client/src/pages/Execution.tsx` → The `task:complete` handler should set `setStatus(payload.status)` which should make `isRunning` false and hide the spinner

**Likely fix:** Add logging to `_handle_exit` and `_complete_task`. The opencode process might stay alive (not exiting after the response), or the stdout reader might not reach its `finally` block. May need to add a timeout or explicitly check the process status.

### 🔴 BUG 2: Reply input disabled during task execution

**File:** `client/src/pages/Execution.tsx`
**What happens:** The reply textarea is disabled while `isRunning` is true. But because of Bug 1, `isRunning` is always true, so the user can never type a follow-up.
**Fix:** Fix Bug 1 first. Then the reply input will enable when the task completes.

### 🟡 BUG 3: Status stuck on "Starting..." initially

**File:** `client/src/pages/Execution.tsx`
**What happens:** The header shows "Starting..." and only changes to "Agent is responding..." when the first message arrives. It should change to "Running" when the process spawns.
**Fix:** The adapter emits a `task:progress` with `stage: "starting"` but the Execution page should also listen for tool events to know the agent is active.

### 🟡 BUG 4: Parser may not parse opencode output correctly

**File:** `server/swiftagent/engine/parser.py`
**What happens:** The parser was written for NDJSON output (the original `--json` flag idea), but `opencode run` doesn't output NDJSON. It outputs plain text (the agent's response) mixed with ANSI escape codes.
**Root cause:** The parser expects structured JSON lines but gets raw terminal output with ANSI color codes.
**Evidence:** The first run showed ANSI-encoded ASCII art and help text dumped to the UI.
**Fix:** Either:
  - (a) Find out if `opencode run` supports a `--json` or `--output json` flag for structured output
  - (b) Strip ANSI codes from stdout and treat all stdout as plain assistant text
  - (c) Rewrite the parser to handle raw text output from `opencode run`

### 🟡 BUG 5: Double API calls

**File:** `client/src/pages/Execution.tsx`
**What happens:** Looking at the server logs, each API call appears twice (two GET requests for the same task ID). This is likely caused by React StrictMode double-mounting in development.
**Fix:** Either disable StrictMode in development or add proper abort controllers / deduplication. Not critical but wasteful.

---

## What Is Completely Missing

### 🔴 MISSING: File Management Features

The app has NO file management capabilities. It should support:
- Browse files in the workspace
- Create, edit, delete files
- Sort and rename files based on rules
- Move files between directories
- Show file contents in the UI

**Where to build:** 
- Backend: Add file operation endpoints in `routes.py` (list dir, read file, write file, delete file, move file)
- Backend: All file operations MUST be restricted to `~/.swiftagent/workspace`
- Frontend: Create a file browser component/page

### 🔴 MISSING: Document Writing

The app cannot write or edit documents. It should support:
- Create documents from prompts
- Summarize existing documents
- Rewrite/edit documents
- Save documents to workspace

**Where to build:** This should work through the agent (opencode) if the agent is properly connected. The issue is that the agent's output isn't being handled correctly (see Bug 4).

### 🔴 MISSING: Tool Connections (MCP)

The `server/swiftagent/tools/` directory is empty. The app should support:
- MCP (Model Context Protocol) tools
- Connections to Notion, Google Drive, Dropbox
- Local API integrations
- The original `base/accomplish` had MCP tools in `packages/agent-core/src/internal/tools/`

**Where to build:**
- `server/swiftagent/tools/` — implement MCP tool handlers
- The adapter should pass MCP tool configs to the opencode CLI

### 🔴 MISSING: Custom Skills / Workflows

No skill/workflow system exists. It should support:
- Define repeatable workflows (sequences of actions)
- Save workflows as named "skills"
- Execute skills by name
- Parameterize skills

### 🔴 MISSING: Permission System UI

The WebSocket handler has `permission:request` and `permission:response` events, but there's no UI for it. When the agent wants to do something dangerous (delete a file, run a command), the user should see a popup asking "Allow this action? [Yes/No]".

**Where to build:**
- Frontend: Create a permission dialog component
- Frontend: Listen for `permission:request` events in Execution.tsx
- Frontend: Send `permission:response` back via WebSocket

### 🔴 MISSING: Settings Page

The sidebar has a Settings nav item but there's no Settings page. It should show:
- Active provider selection
- API key management (add/remove/update per provider)
- Model selection dropdowns
- Ollama configuration
- Theme toggle (light/dark)

### 🟡 MISSING: Proper Error Handling

- No toast/notification system for errors
- No retry logic for failed API calls
- No user-friendly error messages
- Backend errors just print to console

### 🟡 MISSING: Dark Mode

CSS variables for dark mode are defined in `index.css` but there's no toggle. The `.dark` class is never applied.

---

## File-by-File Reference

### Backend (Python)

| File | Lines | What It Does | Status |
|---|---|---|---|
| `main.py` | 98 | FastAPI app, lifespan (loads .env, inits DB, auto-imports keys), CORS, health check | ✅ Works |
| `cli.py` | 175 | Interactive onboard wizard + `--show` status display | ✅ Works |
| `config.py` | 115 | Stdlib .env parser, env provider/key accessors, auto-import into SecureStorage | ✅ Works |
| `api/routes.py` | 215 | REST endpoints: tasks CRUD, settings, providers (catalog, connect/disconnect, models), API keys, onboard status | ✅ Works |
| `api/websocket.py` | 173 | WebSocket endpoint + ConnectionManager (broadcast, permissions, questions, session resume) | ✅ Works |
| `engine/adapter.py` | 290 | Spawns `opencode run "prompt"` subprocess, reads stdout/stderr, emits events | ⚠️ BUGGY — exit not handled, parser wrong |
| `engine/manager.py` | 118 | Task lifecycle — start, cancel, resume, queue management | ⚠️ Untested — depends on adapter |
| `engine/parser.py` | ~150 | NDJSON stream parser — parses lines into MessageType enums | ⚠️ WRONG — opencode run doesn't output NDJSON |
| `models/provider.py` | 220 | ProviderId enum (7), default models (13 total), labels, env var mappings, catalog model | ✅ Works |
| `models/events.py` | 83 | WSEventType enum (server→client + client→server), event/payload models | ✅ Works |
| `models/task.py` | ~80 | Task, TaskConfig, TaskMessage, TaskResult, TaskStatus models | ✅ Works |
| `models/settings.py` | ~30 | AppSettings model | ✅ Works |
| `storage/database.py` | ~120 | SQLite init with WAL, migrations, connection management | ✅ Works |
| `storage/secure.py` | ~100 | AES-256-GCM encrypted storage for API keys | ✅ Works |
| `storage/tasks.py` | ~80 | Task CRUD — save, get, list, delete, update status, add message | ✅ Works |
| `storage/settings.py` | ~60 | App settings get/set operations | ✅ Works |
| `storage/providers.py` | ~60 | Provider settings — connect, disconnect, set active, update model | ✅ Works |
| `tools/__init__.py` | 0 | Empty — MCP tools not implemented | ❌ Missing |

### Frontend (TypeScript/React)

| File | Lines | What It Does | Status |
|---|---|---|---|
| `main.tsx` | 10 | React entry point | ✅ Works |
| `App.tsx` | 12 | Root — connects WebSocket on mount, renders router | ✅ Works |
| `router.tsx` | 18 | React Router: `/` (Home), `/task/:taskId` (Execution), `/history` (History) | ✅ Works |
| `components/layout/Layout.tsx` | ~60 | Sidebar with Tasks, History, Settings nav items | ✅ Works |
| `lib/swiftagent.ts` | 246 | REST client (fetch-based) + WebSocket client (auto-reconnect, typed events) | ✅ Works |
| `lib/utils.ts` | 6 | `cn()` class merge helper | ✅ Works |
| `pages/Home.tsx` | ~160 | Task launcher — animated textarea, send button, starts task via WS | ✅ Works |
| `pages/Execution.tsx` | ~270 | Task view — messages, status, reply input | ⚠️ BUGGY — infinite loop |
| `pages/History.tsx` | ~170 | Task list with delete, clear all, status icons | ✅ Works |

---

## How the Engine Works (and Why It's Wrong)

### Current Flow

```
User types "Hello" in Home.tsx
    → WebSocket sends { type: "task:start", payload: { prompt: "Hello" } }
    → websocket.py receives, calls task_manager.start_task()
    → manager.py creates Task, saves to DB, creates OpenCodeAdapter
    → adapter.py spawns: `opencode run "Hello"` in ~/.swiftagent/workspace
    → adapter reads stdout line by line → feeds to parser.py
    → parser tries to parse JSON lines (NDJSON format)
    → parser emits ParsedMessages → adapter broadcasts WSEvents
    → Execution.tsx receives events, renders messages
```

### What's Wrong

1. **`opencode run` does NOT output NDJSON.** It outputs plain text (the agent's conversational response) mixed with ANSI escape codes from the terminal. The parser is looking for JSON and fails silently, meaning most output is lost or garbled.

2. **The process exit is not detected properly.** The `_read_stdout()` coroutine reads until EOF, then calls `_handle_exit()`. But if opencode keeps stdout open (e.g., waiting for input, or not flushing), the reader blocks forever → the task never completes → the UI shows "Agent is responding..." forever.

3. **The session model is wrong for "run" mode.** `opencode run` is a one-shot command — it takes a message, the agent responds, and it exits. There's no interactive session. To have a back-and-forth conversation, each follow-up needs a new `opencode run --session <id> --continue` subprocess. This is partially implemented but never tested.

### What Needs to Happen

**Option A: Fix the `opencode run` approach**
- Strip ANSI codes from stdout
- Treat all stdout as plain assistant text (not NDJSON)
- Add explicit process timeout handling
- Properly detect when the process exits
- Test session continuation with `--session` and `--continue` flags

**Option B: Use `opencode serve` + HTTP/WebSocket**
- OpenCode has a `serve` command that starts a headless server
- SwiftAgent could connect to it via HTTP/WebSocket instead of subprocess
- This would give proper structured output and interactive sessions
- This is the more robust approach but requires understanding the opencode serve API

**Option C: Drop opencode entirely and use LLM APIs directly**
- Use the LLM provider (OpenAI, Anthropic, etc.) API directly
- Implement tool calling (function calling) for file operations, commands, etc.
- This gives full control but requires implementing the agent logic from scratch
- This is the most work but the most reliable

---

## Git History

```
4446048 feat: add chat reply input to Execution page + session resumption
45fd6d4 fix: use correct 'opencode run' subcommand + sandbox all tasks to ~/.swiftagent/workspace
1ca4dca docs: fix README author name, remove wrong ecosystem ref, add MIT LICENSE
db67746 docs: add comprehensive SEO-optimized README with beginner-friendly setup guide
e4e530e feat: expand to 7 LLM providers + onboard CLI + .env config
40ea1de feat: initial SwiftAgent project — Python FastAPI backend + React Vite frontend
6621258 chore: add Python .gitignore
```

---

## How to Run

### Prerequisites
- Python 3.10+
- Node.js 18+
- `opencode` CLI installed (`npm i -g opencode-ai`)

### Setup
```bash
make install          # Install Python + Node deps
make onboard          # Interactive provider setup (creates .env)
make onboard-show     # Check config status
```

### Run
```bash
make dev              # Start server (port 8000) + client (port 5173)
make dev-server       # Server only
make dev-client       # Client only
```

### Data locations
- **Database:** `~/.swiftagent/swiftagent.db`
- **Encrypted keys:** `~/.swiftagent/keyring.json`
- **Agent workspace (sandbox):** `~/.swiftagent/workspace/`
- **Config:** `<project-root>/.env`

---

## Recommendations for the Next Developer

### Priority 1: Fix the agent engine (adapter.py + parser.py)

This is the #1 blocker. The agent can't work properly until the engine correctly:
1. Spawns `opencode run`
2. Reads and parses the output
3. Detects when the process exits
4. Broadcasts the correct events

**Steps:**
1. Run `opencode run "Hello"` manually in a terminal and observe the raw output format
2. Check if `opencode run --help` reveals a `--json` or `--format` flag
3. If no JSON mode: strip ANSI codes and treat stdout as plain text
4. Add proper process lifecycle logging to see exactly where it gets stuck
5. Add a process timeout (e.g., 5 minutes max per task)

### Priority 2: Build the permission approval UI

The backend supports `permission:request` / `permission:response` but the frontend has no dialog for it. This is critical for the "Full Control" feature — users need to approve file writes, command executions, etc.

### Priority 3: Build the Settings page

Add provider selection, API key management, model dropdowns, theme toggle.

### Priority 4: Build File Management

REST endpoints for file operations within the sandbox, plus a file browser in the frontend.

### Priority 5: Add MCP tool connections

Implement the `tools/` module with MCP handlers for Notion, Google Drive, etc.

### Priority 6: Custom Skills / Workflows

Build a workflow definition and execution system.

---

## Environment & Dependencies

### Python (server/requirements.txt)
```
fastapi>=0.115
uvicorn[standard]>=0.34
pydantic>=2.10
cryptography>=44.0
```

### Node.js (client/package.json — key deps)
```
react 19, react-router 7, zustand 5
framer-motion 12, @phosphor-icons/react
react-markdown, remark-gfm
tailwindcss 3, @tailwindcss/typography
class-variance-authority, clsx, tailwind-merge
```

---

## Summary

**Built:** Backend infrastructure (API, DB, auth, providers, config, CLI) + Frontend skeleton (3 pages, API client, WebSocket).

**Broken:** The core agent engine — subprocess management, output parsing, task lifecycle. The app is fundamentally incapable of completing tasks reliably right now.

**Missing:** File management, document writing, tool connections (MCP), custom skills, permission UI, settings page, error handling, dark mode toggle.
