# Architecture

SwiftAgent intentionally has one local process boundary rather than a distributed control plane.

## Runtime flow

1. The React app opens a WebSocket to the local FastAPI server.
2. `TaskManager` validates a bounded task request and, when requested, verifies that its working directory remains inside the selected workspace.
3. At most five adapters run simultaneously; up to 25 additional tasks wait FIFO. Completion releases the next task.
4. The registry selects an adapter from `agent_id`; the task manager never imports a specific coding-agent implementation.
5. The adapter owns discovery, native arguments, process/session lifecycle, parsing, and translation into versioned SwiftAgent events.
6. A strict task uses bwrap or fails before process launch. A user can explicitly choose fallback mode on a trusted machine.
7. On shutdown, adapters are cancelled. On the next startup, unfinished task records are marked failed with a resumption hint rather than pretending to be live.

## Agent boundary

`TaskManager` depends only on the `AgentAdapter` protocol. Every registry entry declares stable agent and adapter IDs, an adapter version, transport, local status probe, and a capability snapshot. Those values are persisted with every run so history stays interpretable after adapters evolve.

Adapters emit a small normalized vocabulary (`run.started`, messages, tools, approvals, questions, plans, usage, and terminal events) while retaining bounded native metadata for diagnosis. Legacy browser events remain temporarily available during the v0.x UI migration.

Concrete adapters live under `swiftagent/agents/`. Claude Code preserves its native stream-JSON behavior, while the ACP v1 client uses the official SDK to negotiate compatible local agents over stdio. Codex, OpenCode, and generic-command integrations plug into the same boundary; they do not add agent-specific branches to the task manager.

## Storage and boundaries

- SQLite database: `~/.swiftagent/swiftagent.db` by default, configurable with `SWIFTAGENT_DATA_DIR`.
- Workspace: `~/.swiftagent/workspace` by default. The Files API resolves every path against this root and rejects escapes.
- Browser: local by default. The backend does not implement authentication or multi-user authorization.

## Scaling notes

The practical unit is one developer workstation. SQLite WAL, indexes, bounded history responses, capped file payloads, a capped queue, and subprocess cleanup cover that workload without pretending to be a multi-tenant scheduler. A future remote deployment would need authentication, per-user isolation, durable queue ownership, and a separate security model.
