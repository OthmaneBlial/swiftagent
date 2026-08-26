# Changelog

All notable changes are documented here. This project follows semantic versioning for public releases.

## 0.2.0 — 2026-08-26

- Fail closed when strict bwrap sandboxing is unavailable instead of silently running unsandboxed.
- Add task queue draining, restart recovery, terminal-result persistence, process-group cleanup, and bounded history.
- Harden workspace file operations with size limits, atomic writes, overwrite/root-deletion guards, and clearer errors.
- Add local production serving, readiness checks, request IDs, examples, contribution/security policies, and CI.

## 0.1.0

- Initial Claude-only local FastAPI and React implementation.
