# Historical SwiftAgent progress snapshot (pre-v0.3)

> Last updated: 2026-03-02  
> Historical note only: this file describes the original Claude-only phase.
> The current agent-agnostic implementation and validation status live in
> [README.md](README.md), [ROADMAP.md](ROADMAP.md), and
> [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## Completed in this milestone

### Engine and lifecycle
- Replaced the legacy execution path with Claude CLI stream-json adapter.
- Parser now handles Claude `system`, `assistant`, `user/tool_result`, and `result` events.
- Task completion now finalizes from parsed `result` events.
- Process-exit fallback now marks task failed if no `result` was emitted.
- Added timeout guard and safer adapter cleanup in task manager.

### Safety model
- Added workspace path resolver/guard for all file endpoints.
- Added Linux strict sandbox launch via `bwrap` (with fallback when unavailable).
- Added engine status endpoint exposing CLI/sandbox/auth probe health.
- Tool-use and tool-result activity is persisted to task message metadata.

### Settings and onboarding
- Migrated settings to Claude-focused contract:
  - `theme`
  - `debug_mode`
  - `claude_model`
  - `claude_permission_mode`
  - `claude_cli_path`
  - `workspace_dir`
  - `sandbox_mode`
- Updated onboarding CLI for Claude readiness checks and setup flow.
- Removed runtime dependence on provider/key onboarding.
- Fixed dotenv parsing behavior for inline comments and blank values.

### Frontend reliability and features
- Reworked execution page state machine for reliable running/completion flow.
- Added permission/question dialog wiring.
- Added strict-mode-safe GET request deduping and WS connection ref counting.
- Added Settings page (Claude config, workspace/sandbox, theme, engine health).
- Added Files page (browse/read/write/mkdir/move/delete within workspace).
- Added toast-based error handling and dark mode application from settings.
- Added navigation/routes for Settings and Files.

### API surface
- Added `GET /api/engine/status`.
- Added workspace-scoped file APIs under `/api/files/*`.
- Provider/key endpoints are now explicitly deprecated (`410 Gone`).

## Deferred to phase 2

- External connectors (Notion, Google Drive, Dropbox).
- Advanced custom skill/workflow orchestration beyond direct Claude CLI use.

## Validation status

- Client build: passing.
- Client lint: passing.
- Python tests: no server tests currently defined in repository.
