# Demo capture guide

SwiftAgent needs no hosted demo because it is local-first. To record a reproducible product demonstration:

1. Run `make dev` with a disposable workspace.
2. In Settings, show the engine status and either a working strict sandbox or the explicit fallback warning.
3. Start a harmless task such as “Create `hello.md` with a two-line project note.”
4. Capture the live tool activity, final task summary, Files view, and task history.
5. Store a redacted GIF or MP4 in `docs/images/` and link it from the README. Never record prompts, paths, or tokens from a personal workspace.
