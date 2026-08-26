# OpenCode adapter research plan

1. Confirm the current official ACP, CLI JSON-run, models, provider, resume, and
   sharing semantics from OpenCode primary documentation.
2. Inspect the installed CLI using free, read-only probes only.
3. Perform one local ACP initialize/new-session handshake without a model prompt.
4. Prefer the shared ACP client; define an honest, reduced JSON-run fallback.
5. Freeze both transports with deterministic fixtures and verify cancellation,
   malformed events, model discovery, and no automatic sharing.
