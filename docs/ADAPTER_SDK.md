# Adapter developer guide

SwiftAgent Adapter API `1.0` is an independently versioned, out-of-process
extension boundary. An external contributor can connect an installed local ACP
v1 agent by adding a validated manifest; no task-manager, API route, database,
or React code change is required.

## Why the boundary is ACP and a manifest

Loading arbitrary Python plugins into the local server would give third-party
code the server's filesystem, database, and process privileges. SwiftAgent
instead keeps the integration in a subprocess and reuses its workspace-scoped
ACP client. The manifest is configuration, not an installer:

- it contains a literal argv, never a shell command;
- it cannot replace a registered built-in ID;
- it can forward only allowlisted environment variables plus a small process
  baseline (`HOME`, `LANG`, `LC_ALL`, `PATH`, `TMPDIR`);
- it cannot self-assign verified external isolation;
- it is loaded only from the user's local adapter directory at startup; and
- it cannot download, install, update, or execute marketplace code by itself.

## API and migration policy

`adapter_api_version` is independent from the SwiftAgent application version.
The current exact value is `1.0`.

- Patch application releases may add optional manifest fields or normalized
  metadata without changing Adapter API `1.0`.
- A new required field, removed event, changed capability meaning, or breaking
  launch/authentication rule requires a new adapter API major/minor and a
  migration note.
- SwiftAgent rejects unsupported API versions before registering the command.
- Manifests reject unknown fields so a typo cannot silently weaken a policy.
- A compatibility report covers only its listed agent/adapter versions and
  operating systems; it does not roll forward automatically.

## Manifest anatomy

The authoritative schema is
`adapter-kit/schema/adapter-manifest-v1.schema.json`. Core fields are:

| Field | Meaning |
| --- | --- |
| `agent_id` | Stable user-facing integration identity; cannot collide with a built-in. |
| `adapter_id` / `adapter_version` | Translation implementation identity persisted in every run. |
| `protocol` | `acp-v1` in Adapter API 1.0. |
| `command` | Literal bounded argv. `${manifest_dir}` and `${python}` are the only substitutions. |
| `environment_allowlist` | Additional environment names forwarded deliberately. |
| `state_directories` | Documentation/evidence only; never auto-mounted writable. |
| `capabilities` | Conservative maximum exposed to the UI and saved with the run. |
| `version_probe` | Optional free, bounded local command/regex; no model prompt. |
| `compatibility` | Exact versions, OS scope, contract result, date, and evidence references. |
| `contract` | Deterministic fixture input, expected events, and optional cancel scenario. |

## Capability mapping and UI behavior

Declare a capability only when the contract fixture or a redacted live receipt
shows it. SwiftAgent uses the declaration before a run and persists the
negotiated snapshot during the run.

| Manifest capability | Normalized evidence | UI effect |
| --- | --- | --- |
| `session_resume` | native session ID plus successful load | enables resume only for the same agent |
| `tool_events` | `tool.started` / `tool.completed` | tool activity and receipt counts |
| `approvals` | request and resolved outcome | interactive approval dialog |
| `questions` | request and resolution | question UI when supported |
| `plan_updates` | `plan.updated` | latest plan in the receipt |
| `usage` | `usage.updated` | native usage evidence, never invented cost |
| `model_discovery` / `mode_discovery` | negotiated options | model/mode controls |
| `attachments` | negotiated types plus send-path fixture | attachment controls |
| `native_sandbox` | native protocol/config evidence | native safety card only |
| `external_sandbox` | host integration evidence | SwiftAgent isolation card only |

Unsupported controls remain hidden or disabled. Cross-agent continuation always
uses a reviewed handoff preview; native session formats never cross adapters.

## Authentication and state

Authenticate with the agent's own CLI before running SwiftAgent. The ACP client
may invoke a protocol-declared non-secret auth method, but terminal login and
provider credentials stay outside SwiftAgent.

`state_directories` documents where the agent expects state. Adapter API 1.0
does not make those paths writable inside strict isolation. If the agent needs
to mutate login state, complete login before the run or document why a future
reviewed isolation policy is needed. Never add a broad home-directory bind.

Environment forwarding is opt-in. Prefer agent-owned state over API keys in the
environment. If a credential variable is unavoidable, name it explicitly in
the compatibility report and keep it out of logs, events, fixtures, receipts,
and screenshots.

## Lifecycle, cancellation, and limits

The shared ACP adapter owns the process group. Cancellation sends ACP cancel,
waits briefly for a terminal response, then terminates/kills the process group
if required. Shutdown and restart recovery cannot leave a false live task.

Manifests are capped at 256 KiB and 64 literal command arguments. ACP frames,
stderr retention, file reads/writes, terminal count, terminal arguments,
terminal environment, and terminal output are bounded by the shared client.
Workspace callback paths must be absolute and contained by the selected root.
Strict mode wraps the command with Bubblewrap or fails closed; fallback is
explicitly unisolated.

## Contract harness

Run:

```bash
PYTHONPATH=server server/.venv/bin/python \
  -m swiftagent.adapter_sdk.contract \
  --manifest path/to/example.adapter.json \
  --output path/to/contract-report.json
```

The harness uses a temporary workspace/database, automatic fixture-only
approval, and no network requirement. It validates:

- agent/adapter identity on normalized events;
- new-session completion and terminal persistence;
- normalized evidence for every declared event capability;
- native-session persistence and resume when declared;
- cancellation and terminal cancelled state when a cancel fixture is supplied;
- literal command launch, bounded environment forwarding, and no shell.

A passing JSON report is test evidence, not endorsement. Submit it with the
compatibility template and security checklist. Built-in or community trust is
assigned by SwiftAgent review policy, never by a manifest assertion.

Trust fields are deliberately absent from the public manifest schema. Every
manifest-loaded integration remains `local custom`, including one with a passing
compatibility declaration. See the [adapter trust policy](ADAPTER_TRUST.md) for
the separate maintainer review gate.

## First adapter walkthrough

1. Copy `adapter-kit/example-adapter/`.
2. Replace the fake agent while keeping a deterministic fixture mode.
3. Change every stable identity/version field.
4. Reduce capabilities to what the fixture already proves.
5. Add version/auth/state documentation and a free version probe.
6. Run the contract harness until it produces a passing report.
7. Test failure, malformed output, timeout, and unsupported paths.
8. Complete the security and compatibility templates.
9. Copy the reviewed local files into the adapter directory and restart.
10. Inspect readiness, capability chips, a receipt, and a redacted handoff in
    the browser before proposing broader verification.
