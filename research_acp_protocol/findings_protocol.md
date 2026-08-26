# ACP protocol findings

Researched on 2026-08-26 from primary protocol and SDK sources.

## Stable target

- The current stable schema release is
  [`schema-v1.21.0`](https://github.com/agentclientprotocol/agent-client-protocol/releases/tag/schema-v1.21.0).
- The wire protocol remains version `1`, uses JSON-RPC 2.0 over standard
  input/output for local agents, camelCase field names, snake_case
  discriminants, and absolute filesystem paths.
- The official Python SDK package is
  [`agent-client-protocol`](https://github.com/agentclientprotocol/python-sdk).
  SwiftAgent pins the compatible `0.12.x` line and uses its generated Pydantic
  models on both sides of the deterministic contract fixture.

## Implemented lifecycle

The client executes `initialize`, optional agent-owned authentication,
`session/new` or `session/load`, and `session/prompt`. It accepts stable
`session/update` notifications, handles permission requests, file callbacks,
terminal callbacks, and sends `session/cancel` before process termination.

SwiftAgent advertises only callbacks it implements. It does not advertise
terminal authentication or elicitation. Terminal-only authentication produces
an actionable handoff to the agent's official login flow; credentials are not
copied into SwiftAgent.

## Safety decisions

- Local stdio only; remote ACP needs a separate authentication, TLS,
  authorization, and workspace design.
- Every client file path must be absolute and stay inside the selected task
  workspace after resolution.
- Agent and callback subprocesses use literal argv arrays and no shell.
- Reads, writes, terminal count, environment, arguments, retained output,
  native metadata, handshake time, and cancellation grace are bounded.
- Negotiated capability snapshots and native session IDs are persisted with
  each run so the UI and history do not claim features the agent did not
  advertise.

## Conformance evidence

`server/tests/fixtures/acp/fake_agent.py` uses the official SDK to cover new
and loaded sessions, messages, thought separation, tool and plan updates,
permission selection, file read/write, terminal execution/output/release,
usage, normal completion, and cancellation. The adjacent transcript records
the exact stable schema source used by the fixture.
