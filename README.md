# SwiftAgent

> A local, workspace-scoped control room for running, reviewing, and resuming coding-agent tasks.

SwiftAgent gives developers one calm interface for local coding agents: choose an adapter, start a task, watch live tool activity, inspect the workspace, and keep durable local history. It is designed for one developer and one trusted machine—not a hosted multi-user agent platform.

![Local-first](https://img.shields.io/badge/privacy-local--first-176B87) ![Python](https://img.shields.io/badge/backend-FastAPI-009688) ![React](https://img.shields.io/badge/frontend-React-149ECA) ![License](https://img.shields.io/badge/license-MIT-2F855A) [![CI](https://github.com/OthmaneBlial/swiftagent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OthmaneBlial/swiftagent/actions/workflows/ci.yml)

**[Visit the live project site →](https://othmaneblial.github.io/swiftagent/)**

## Why SwiftAgent

Point SwiftAgent at a project folder, choose an available agent, and describe the outcome. Responses, tool calls, safety state, and final results stay in one local timeline. When an adapter proves native resume support, a later follow-up can continue that session instead of starting from zero.

## Try it locally

Prerequisites: Python 3.11+, Node.js 18+, and at least one installed coding agent supported by an enabled adapter.

```bash
git clone https://github.com/OthmaneBlial/swiftagent.git
cd swiftagent
make setup
make onboard
make dev
```

Open `http://127.0.0.1:5173`, choose a detected integration, and review **Your agents → Workspace & safety** before doing sensitive work. For a production-style local launch, FastAPI can serve the built web bundle:

```bash
make start
# http://127.0.0.1:8000
```

## What it does

- Selects adapters through a stable agent registry and exposes only declared capabilities.
- Normalizes native streams into versioned message, tool, approval, question, plan, usage, and terminal events.
- Stores task history, agent/adapter identity, capability snapshots, messages, results, and native session IDs in local SQLite.
- Browses, creates, moves, and deletes UTF-8 files only inside the configured workspace.
- Enforces bounded prompts, history pages, directory listings, and file reads/writes.
- Queues up to 25 tasks after five active executions; queued work starts automatically as a slot frees.
- Uses atomic workspace file edits and refuses silent overwrites or workspace-root deletion.
- Provides readiness, health, engine/sandbox diagnostics, request IDs, and actionable failure messages.

## Safety model

SwiftAgent defaults to `strict` sandbox mode. A task **will not start** unless Linux `bwrap` is installed and usable; strict mode never silently downgrades to unsandboxed execution.

`fallback` is an explicit, less-safe choice for a trusted local machine. An agent process is not OS-isolated in fallback mode, so it may access files permitted to your local user account. The Files page remains workspace-scoped in both modes, but that API guard is not a substitute for OS isolation of the agent process.

SwiftAgent binds to `127.0.0.1` by default. It refuses a non-loopback host unless `SWIFTAGENT_ALLOW_REMOTE=1` is deliberately set behind a trusted authentication and transport-security layer. It does not provide multi-user authentication.

Read the [security policy](SECURITY.md) before opening an issue about a vulnerability, and see [the bwrap recovery guide](BWRAP_SANDBOX_ROADMAP.md) when strict mode is unavailable.

## Configuration

Use [`.env.example`](.env.example) as the reference. Environment settings establish defaults; values saved in Settings take precedence for app preferences.

| Setting | Default | Purpose |
| --- | --- | --- |
| `SWIFTAGENT_WORKSPACE_DIR` | `~/.swiftagent/workspace` | Dedicated root for Files and task working directories. |
| `SWIFTAGENT_SANDBOX_MODE` | `strict` | `strict` requires working bwrap; `fallback` is explicit and unisolated. |
| `SWIFTAGENT_ACP_COMMAND_JSON` | empty | Literal argv array for a local ACP v1 agent, for example `["your-agent", "acp"]`. |
| `SWIFTAGENT_TASK_TIMEOUT_SEC` | `900` | Per-task timeout in seconds. |
| `SWIFTAGENT_MAX_FILE_BYTES` | `1048576` | Maximum UTF-8 file read/write size. |
| `SWIFTAGENT_MAX_DIRECTORY_ENTRIES` | `500` | Maximum entries returned to the file browser. |
| `SWIFTAGENT_ALLOW_REMOTE` | `0` | Must be `1` before a non-loopback server host is accepted. |

The browser’s “Your agents” page chooses a default integration, adapter options, workspace, sandbox mode, and theme. Adapter-specific permission bypasses should be used only when their native consequences are understood.

## CLI and examples

After `make setup`, the server package exposes:

```bash
server/.venv/bin/swiftagent onboard --show
server/.venv/bin/swiftagent onboard
server/.venv/bin/swiftagent run
```

Two executable protocol examples are included for automation experiments:

```bash
python3 examples/basic/start_task.py "Summarize the files in this workspace"
python3 examples/advanced/resume_session.py <session-id> "Now propose the smallest safe change"
```

They connect to a running local server and print the task event stream.

## API

The browser communicates with a local REST and WebSocket API. Useful operational endpoints include:

- `GET /health` — liveness
- `GET /ready` — local readiness and workspace availability
- `GET /api/agents` — detected integrations, versions, readiness, and capabilities
- `GET /api/engine/status` — deprecated Claude compatibility and sandbox diagnosis
- `GET /api/tasks?limit=50&offset=0` — bounded task history
- `GET /api/files/list?path=.&limit=200` — bounded workspace directory listing
- `ws://127.0.0.1:8000/ws` — `task:start`, `task:cancel`, and `session:resume`

All file mutations are under `/api/files/*`; traversal, root deletion, silent target overwrite, non-UTF-8 reads, and oversized text payloads are rejected.

## Architecture

```text
React + Vite browser UI
        │ REST + WebSocket
        ▼
FastAPI ── Task manager ── Agent registry ── selected local adapter
   │                                  │
   │                                  └── native stream → normalized events
   └── SQLite history/settings and workspace-scoped file API
```

More detail: [architecture](docs/ARCHITECTURE.md) · [ACP adapter](docs/ACP_ADAPTER.md) · [Codex adapter](docs/CODEX_ADAPTER.md) · [demo capture guide](docs/DEMO.md).

## Quality checks

```bash
make lint   # Ruff + ESLint
make test   # Python regression tests + React typecheck/build
make build  # production web bundle
```

The server regression suite covers adapter contracts, capability combinations, lifecycle persistence/recovery, schema migration, task queue draining, strict-sandbox fail-closed behavior, file containment, size limits, and destructive-action guards.

## Adapter availability

The v0.3 release ships the migrated Claude Code adapter and the agent-neutral extension boundary. The in-development v0.4 line now includes tested local ACP v1 and native Codex app-server adapters; inspect their readiness and effective capabilities in **Your agents**. OpenCode and a conservative generic-command adapter remain tracked deliverables in [ROADMAP.md](ROADMAP.md) and are not presented as working until their own fixtures and live matrix pass.

## Contributing and release notes

Read [CONTRIBUTING.md](CONTRIBUTING.md) for local setup and the contribution workflow. Changes are tracked in [CHANGELOG.md](CHANGELOG.md). This project is MIT-licensed; see [LICENSE](LICENSE).

Suggested GitHub metadata: **“Local control room for coding agents, with durable history and explicit safety”**; topics `coding-agents`, `ai-agent`, `codex`, `opencode`, `acp`, `local-first`, `developer-tools`, `sandboxing`.
