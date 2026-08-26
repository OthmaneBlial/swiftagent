# Changelog

All notable changes are documented here. This project follows semantic versioning for public releases.

## 0.3.0 — 2026-08-26

- Replace the Claude-specific task core with an agent registry, capability contracts, normalized events, and adapter-owned process lifecycles.
- Preserve existing task history through a forward-only SQLite migration that records agent, adapter, version, native session, and capability identity.
- Move Claude CLI discovery, settings, state paths, stream parsing, and process behavior into the first isolated adapter with golden fixtures.
- Add the agent-aware composer, “Your agents” settings, readiness cards, safety summaries, and agent badges/filtering in execution and history.
- Add read-only, cacheable local agent detection without making paid model calls.

## 0.2.1 — 2026-08-26

- Fix production SPA refreshes so client-side routes such as `/settings` serve the app entry point while missing static assets remain 404s.

## 0.2.0 — 2026-08-26

- Fail closed when strict bwrap sandboxing is unavailable instead of silently running unsandboxed.
- Add task queue draining, restart recovery, terminal-result persistence, process-group cleanup, and bounded history.
- Harden workspace file operations with size limits, atomic writes, overwrite/root-deletion guards, and clearer errors.
- Add local production serving, readiness checks, request IDs, examples, contribution/security policies, and CI.

## 0.1.0

- Initial Claude-only local FastAPI and React implementation.
