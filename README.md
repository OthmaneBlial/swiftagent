# SwiftAgent

SwiftAgent is a local web app for running Claude CLI tasks with task history, live streaming, settings, and workspace-scoped file management.

## Current Architecture

- Backend: FastAPI + SQLite (`server/`)
- Frontend: React + Vite + Tailwind (`client/`)
- Engine: Claude CLI only (`claude -p --verbose --output-format stream-json`)
- Workspace safety:
  - Backend workspace path guard for all file APIs
  - Optional strict Linux sandbox via `bwrap`

## Requirements

- Python 3.11+
- Node.js 18+
- Claude CLI installed and authenticated (`claude --version`)
- Linux strict mode: `bwrap` installed

## Quick Start

```bash
make install
make onboard
make dev
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

## Configuration (`.env`)

Use `.env.example` as reference.

```env
SWIFTAGENT_CLAUDE_PATH=
CLAUDE_MODEL=
CLAUDE_PERMISSION_MODE=default
SWIFTAGENT_WORKSPACE_DIR=
SWIFTAGENT_SANDBOX_MODE=strict
SWIFTAGENT_PORT=8000
SWIFTAGENT_HOST=127.0.0.1
SWIFTAGENT_DEV=0
SWIFTAGENT_NO_BROWSER=0
SWIFTAGENT_DATA_DIR=
```

## CLI

```bash
make onboard       # interactive Claude setup
make onboard-show  # Claude + sandbox readiness status
```

## REST API

- `GET /health`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`
- `DELETE /api/tasks`
- `GET /api/settings`
- `PUT /api/settings`
- `GET /api/engine/status`
- `GET /api/files/workspace`
- `GET /api/files/list?path=.`
- `POST /api/files/read`
- `POST /api/files/write`
- `POST /api/files/mkdir`
- `POST /api/files/move`
- `POST /api/files/delete`

Deprecated provider/key APIs are kept as `410 Gone`.

## WebSocket

Endpoint: `ws://localhost:8000/ws`

Key events:
- Client -> server: `task:start`, `task:cancel`, `session:resume`, `permission:response`, `question:response`
- Server -> client: `task:started`, `task:progress`, `task:message`, `tool:use`, `tool:result`, `task:complete`, `task:error`, `permission:request`, `question:request`

## Notes

- Task completion is driven by Claude `result` stream events.
- Session continuation uses Claude session IDs (`-r <session_id>`).
- Workspace history is preserved in SQLite; no destructive migration is required.
