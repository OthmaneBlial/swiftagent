# OpenCode adapter findings — 2026-08-26

## Primary sources

- <https://opencode.ai/docs/acp/> documents `opencode acp` as ACP JSON-RPC over
  stdio and lists tools, permissions, project rules, agents, and MCP support.
- <https://opencode.ai/docs/cli/> documents `run --format json`, explicit
  `--session`, `--fork`, `--file`, `--model`, `--variant`, `--auto`, and
  `--share`; it also documents `session list --format json`.
- <https://opencode.ai/docs/models/> defines model IDs as `provider/model` and
  derives availability from configured providers and the current project.

## Local evidence

- Executable: `/Users/othmane/.opencode/bin/opencode`
- Version: `1.18.13`
- `opencode acp --help`: available
- `opencode run --help`: raw JSON event mode available
- `opencode models`: project-dependent `provider/model` identifiers are
  discovered from the configured workspace; no IDs are copied into SwiftAgent
  source code.
- ACP initialize/new-session, with no prompt, negotiated protocol v1, load,
  resume, fork, image, embedded context, model options, and build/plan modes.
- The probe created an unshared local session and made no inference call.

## Decisions

- ACP is the built-in primary transport.
- OpenCode login methods are never invoked automatically by SwiftAgent.
- JSON-run is selected only when ACP is absent and advertises reduced
  capabilities at discovery time and in the persisted run snapshot.
- `--share`, `--auto`, and implicit last-session continuation are prohibited.
- Model IDs come from the CLI or ACP session configuration, never a global
  hard-coded catalog.
