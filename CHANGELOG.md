# Changelog

All notable changes are documented here. This project follows semantic versioning for public releases.

## Unreleased

- Add a text-only generic-command adapter with a reviewed schema-v1 manifest, literal argv/stdin transport, environment allowlist, bounded output/timeout, process-group cleanup, and no shell interpolation.
- Require a matching disposable-workspace test receipt before a generic command can run real tasks; manifest or executable changes disable it automatically.
- Add an ACP-first OpenCode 1.18 adapter with version/transport detection, CLI-owned model discovery, native resume, explicit model configuration, and no automatic session sharing.
- Add a clearly reduced OpenCode JSON-run fallback with bounded parsing, tool/usage mapping, process-group cancellation, and no interactive approvals, plans, questions, auto-approval, or sharing.
- Add a native Codex app-server v2 adapter with free readiness/auth probes, thread start/resume, model discovery, streamed items, approvals, questions, plan/usage mapping, native safety profiles, interruption, and process cleanup.
- Require explicit confirmation before combining Codex `never` approvals with `danger-full-access`, while showing native and SwiftAgent safety as separate layers.
- Add a local ACP v1 client adapter based on the official SDK, with negotiated capabilities, native session creation/loading, permissions, streamed updates, cancellation, and bounded native diagnostics.
- Confine ACP file and terminal callbacks to the selected workspace, use literal command arrays, cap retained output, and preserve strict Bubblewrap fail-closed behavior.
- Add settings UI, stable schema evidence, and a deterministic ACP fake-agent contract suite.

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
