# Contributing to SwiftAgent

Thanks for improving a local-first tool. Keep changes small, explain the user-facing effect, and preserve the safety model.

## Setup

```bash
make setup
make dev
```

Python lives in `server/`; the React app lives in `client/`. The application entry point initializes SQLite and mounts REST/WebSocket routes. Agent adapters live in `server/swiftagent/agents/`, shared lifecycle and queueing live in `server/swiftagent/engine/`, and workspace containment is in `server/swiftagent/tools/`.

## Development workflow

1. Create a dedicated test workspace rather than using a personal home directory.
2. Make the smallest coherent change, including a regression test for backend behavior or a focused UI verification for client behavior.
3. Run `make lint` and `make test`.
4. For UI work, check keyboard operation, narrow screens, dark mode, empty/loading/error states, and the Settings safety status.
5. Update documentation when behavior, configuration, or safety implications change.

For the public multi-agent workflow fixture, run `make demo-verify`. It must stay
dependency-free, contain no credentials, and preserve the same acceptance task
for Claude Code, Codex, and OpenCode.

For a new out-of-process ACP integration, start with the
[Adapter Kit](adapter-kit/README.md). A proposal must include its validated
manifest, contract report, exact compatibility scope, and completed security
checklist. A manifest never grants itself built-in or community verification.

`strict` must fail closed when bwrap is unavailable. Do not reintroduce automatic unsandboxed fallback or widen workspace paths without a security review.

## Pull requests

Use an imperative, scoped commit subject. In the PR description, state the problem, solution, tests run, and any config or safety impact. Avoid unrelated formatting churn. Never include `.env`, local databases, task transcripts, API keys, or personal workspace files.

For vulnerabilities, do not open a public issue; follow [SECURITY.md](SECURITY.md).
