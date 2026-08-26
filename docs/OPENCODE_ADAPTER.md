# OpenCode adapter

SwiftAgent treats OpenCode as its own built-in integration, not as a Claude Code
alias. Detection is local and read-only: it resolves the executable, reads the
version, checks transport help, and asks `opencode models` for the current
provider/model IDs. It never sends a model prompt merely to show readiness.

## Preferred ACP transport

When available, SwiftAgent starts `opencode acp` as a literal argument array and
uses the shared, official ACP v1 client. The live 1.18.13 handshake verified
session creation/loading, resume, fork, permissions, plans, usage, image and
embedded-context prompt capabilities, plus model and mode configuration options.

The selected `provider/model` must be one OpenCode advertised for that session.
SwiftAgent applies it through ACP's session config option before the prompt. It
does not copy credentials, call an interactive login method, or enable session
sharing. Provider authentication remains owned by `opencode auth login`.

## Reduced JSON fallback

If the installed CLI has no ACP command but does expose
`opencode run --format json`, SwiftAgent can still run a bounded subprocess and
map text, tool, usage, session, failure, and cancellation events. The UI and
capability snapshot explicitly mark these limitations:

- no interactive approvals;
- no questions or plan stream;
- no OpenCode-native sandbox control exposed by SwiftAgent;
- no session fork; and
- no automatic session sharing.

The fallback never adds `--auto`, `--share`, or `--continue`. Resume occurs only
when SwiftAgent is given the exact native session ID. A zero exit with no JSON
events is treated as a failure instead of silently claiming success.

## Safety boundary

OpenCode's permission system and SwiftAgent process isolation are separate.
Strict SwiftAgent mode still requires usable Bubblewrap and fails closed.
Fallback isolation is an explicit trusted-local choice and gives the agent the
same filesystem access as the local user, even though SwiftAgent's own Files API
remains workspace-scoped.

## Verified contract

- OpenCode CLI: `1.18.13` on macOS arm64
- ACP: protocol v1 over JSON-RPC stdio
- JSON fallback: raw JSON events from `opencode run --format json`
- Fixtures: `server/tests/fixtures/opencode/`
- Official references: [ACP](https://opencode.ai/docs/acp/),
  [CLI](https://opencode.ai/docs/cli/), and
  [models](https://opencode.ai/docs/models/)

Other versions with the required command surface are detected but remain
unverified until added to the compatibility matrix. Versions older than the
tested 1.18 contract are blocked.
