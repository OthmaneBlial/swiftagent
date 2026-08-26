# Architecture

SwiftAgent intentionally has one local process boundary rather than a distributed control plane.

## Runtime flow

1. The React app opens a WebSocket to the local FastAPI server.
2. `TaskManager` validates a bounded task request and, when requested, verifies that its working directory remains inside the selected workspace.
3. At most five adapters run simultaneously; up to 25 additional tasks wait FIFO. Completion releases the next task.
4. `ClaudeAdapter` starts the Claude CLI in a new process session, parses line-delimited JSON output, persists messages/results to SQLite, and broadcasts typed events.
5. A strict task uses bwrap or fails before process launch. A user can explicitly choose fallback mode on a trusted machine.
6. On shutdown, adapters are cancelled. On the next startup, unfinished task records are marked failed with a resumption hint rather than pretending to be live.

## Storage and boundaries

- SQLite database: `~/.swiftagent/swiftagent.db` by default, configurable with `SWIFTAGENT_DATA_DIR`.
- Workspace: `~/.swiftagent/workspace` by default. The Files API resolves every path against this root and rejects escapes.
- Browser: local by default. The backend does not implement authentication or multi-user authorization.

## Scaling notes

The practical unit is one developer workstation. SQLite WAL, indexes, bounded history responses, capped file payloads, a capped queue, and subprocess cleanup cover that workload without pretending to be a multi-tenant scheduler. A future remote deployment would need authentication, per-user isolation, durable queue ownership, and a separate security model.
