# SwiftAgent roadmap — one ergonomic control room, any coding agent

> **Product direction:** SwiftAgent is an inspection-first, local control room
> for the coding agents developers already use. Claude Code, Codex, OpenCode,
> ACP-compatible agents, and future integrations should share one calm,
> reviewable workflow without losing their native capabilities or safety
> semantics.

**Last reviewed:** 2026-08-26

**Current baseline:** `v0.3.0` has shipped the agent-neutral registry,
capability and event contracts, isolated Claude Code adapter, forward-only
history migration, and agent-aware interface. The `v0.4.0` work now adds
verified protocol and native adapters without weakening workspace containment,
queueing, cancellation, or strict Bubblewrap behavior.

## The new promise

SwiftAgent should let a developer open one local app, choose an installed
coding agent, select a safe workspace, run a task, approve sensitive actions,
inspect the result, and continue the native session.

The user should not need to memorize whether the underlying integration uses
JSON lines, JSON-RPC, ACP, an app server, or a CLI subprocess. SwiftAgent owns
the ergonomic experience; each adapter owns the translation to its agent.

The promise is **not** that every agent magically has the same features. The
promise is:

- any integration can describe what it supports;
- the interface shows only capabilities that are actually available;
- unsupported behavior is explicit, never simulated or silently weakened;
- rich built-in support exists for Claude Code, Codex, and OpenCode;
- ACP provides the preferred route for adding compatible agents;
- a restricted generic command adapter covers simpler local CLIs; and
- third parties can add adapters without changing SwiftAgent's task manager,
  storage, WebSocket API, or user interface.

## Why the current design must change

Today, engine discovery, CLI arguments, output parsing, session IDs, permission
modes, status messages, settings, and safety directories are all coupled to
Claude Code. Renaming those fields would only hide the coupling.

The main architectural gaps are:

1. **One concrete adapter acts as the engine abstraction.** Process lifecycle,
   Claude arguments, Claude output parsing, and normalized task events live too
   close together.
2. **Settings confuse the app with one agent.** `claude_model`,
   `claude_permission_mode`, and `claude_cli_path` cannot represent multiple
   installed agents or per-workspace defaults.
3. **The event model is not capability-negotiated.** Session continuation,
   approvals, questions, tool events, attachments, plans, usage, and models
   differ by agent. A static UI will either break or make false promises.
4. **Sandbox behavior is agent-specific.** Each agent has different native
   permission controls, state directories, and process requirements.
   Bubblewrap containment and an agent's own sandbox are separate layers and
   must be reported separately.
5. **The task composer is too generic visually and too specific internally.**
   It exposes only a prompt even though the backend contains partial concepts
   for working directories, model selection, attachments, and todos.

## Product principles

- **Agent choice is a first-class input.** The selected agent is visible before,
  during, and after every run.
- **One UX, honest differences.** Normalize concepts such as messages, tools,
  approvals, progress, and completion while preserving agent-specific details
  behind an expandable view.
- **Capabilities drive the interface.** Hide or disable unsupported controls
  with a plain explanation. Never send guessed flags to an agent.
- **The safest effective posture wins.** Display SwiftAgent isolation and the
  agent's native permission/sandbox policy separately, then summarize the
  effective posture.
- **Local by default, sharing by choice.** SwiftAgent does not upload prompts,
  transcripts, receipts, credentials, or workspace files.
- **Credentials stay with the agent.** Reuse each installed agent's official
  authentication flow. SwiftAgent should report readiness without copying API
  keys into its own database.
- **Sessions belong to their originating agent.** Resume them through the same
  adapter. Cross-agent handoff is an explicit, redacted context export, not a
  fake session migration.
- **No destructive source-control magic.** Never silently commit, reset,
  checkout, discard, or overwrite existing work.
- **Extensible does not mean arbitrary shell execution.** Adapter definitions
  are validated, versioned, and executed as argument arrays with bounded input
  and output; user-controlled shell strings are not a plugin system.

## The target architecture

```text
React client
  ├─ Agent setup and capability-aware task composer
  ├─ Unified execution timeline and permission UI
  └─ Local Run Receipt and history
             │ REST + WebSocket
             ▼
FastAPI application core
  ├─ Task/session lifecycle and queue
  ├─ Normalized events and persisted receipts
  ├─ Workspace and Git inspection
  ├─ Safety policy and external process isolation
  └─ Agent registry
       ├─ ACP adapter ────────── any ACP-compatible agent
       ├─ Claude Code adapter ── native stream-json
       ├─ Codex adapter ──────── Codex app-server
       ├─ OpenCode adapter ───── ACP, with native fallback if required
       └─ Generic command ────── restricted baseline integration
```

### Separate the concepts

Use consistent names throughout code, API, UI, database, and documentation:

| Concept | Meaning | Example |
| --- | --- | --- |
| Agent | The coding tool SwiftAgent launches or connects to | Claude Code, Codex, OpenCode |
| Adapter | SwiftAgent integration implementing the agent contract | `codex_app_server`, `acp`, `claude_stream_json` |
| Provider | The model/account backend selected inside an agent | OpenAI, Anthropic, a local model provider |
| Model | The optional model identifier understood by that agent | Adapter-reported value, never globally assumed |
| Session | Native conversation owned by one agent | Codex thread, Claude session, OpenCode session |
| Run | One SwiftAgent execution/turn and its normalized evidence | Prompt through terminal result |

Do not call model providers “agents,” and do not expose a global model dropdown
whose values are sent unchanged to unrelated CLIs.

### Define `AgentAdapter` as the stable boundary

The application core should depend on an interface equivalent to:

```text
probe() -> AgentStatus
capabilities() -> AgentCapabilities
list_models()? -> ModelOption[]
start(run_config, event_sink) -> NativeSession
resume(native_session, run_config, event_sink)? -> NativeSession
respond_to_permission(request_id, decision)?
respond_to_question(request_id, answer)?
cancel(run_id)
dispose()
```

Every adapter declares its identity, version, minimum supported agent version,
transport, authentication status, state-directory needs, and capabilities.

The initial capability vocabulary should include:

- structured streaming;
- native session create/resume/fork;
- tool start/update/result events;
- approval and question requests;
- plan/todo updates;
- attachments and supported content types;
- model and mode discovery;
- usage/cost information;
- native sandbox/permission controls;
- external SwiftAgent sandbox compatibility; and
- graceful cancellation.

Capabilities are descriptive, not promotional. If an adapter cannot prove a
capability against a supported version fixture, it reports `unsupported` or
`unknown`.

### Normalize a small event vocabulary

Adapters translate native events into versioned SwiftAgent events:

```text
run.started
message.delta
message.completed
tool.started
tool.updated
tool.completed
approval.requested
approval.resolved
question.requested
plan.updated
usage.updated
run.completed
run.failed
```

Every normalized event retains `agent_id`, `adapter_id`, native event type,
run/session IDs, timestamp, and a bounded native metadata object for debugging.
Unknown native events are logged safely rather than crashing the run.

Ordering, deduplication, malformed input, output limits, partial JSON, process
exit races, reconnection, and cancellation must be contract-tested once at the
core boundary and then fixture-tested per adapter.

### Make ACP the open extension path

Implement SwiftAgent as an ACP client using the current stable protocol. ACP
already defines capability negotiation, session creation/loading, prompts,
streamed updates, permission requests, cancellation, file operations, and
terminal interaction over JSON-RPC.

This becomes the preferred “works with more agents” path:

- one ACP adapter supports every compatible local agent;
- agent and protocol versions are negotiated during initialization;
- only advertised capabilities reach the UI;
- ACP v1 remains the supported baseline until a newer protocol is stable and a
  compatibility plan exists; and
- remote ACP remains out of scope until authentication, TLS, authorization,
  and remote-workspace semantics receive a separate security design.

### Keep built-in adapters where they add value

Protocol support alone will not cover every important agent immediately.

- **Claude Code:** move the existing CLI discovery, `stream-json` parser,
  permission mapping, and session resumption into a dedicated adapter. Preserve
  behavior with golden fixtures before refactoring.
- **Codex:** use the official app-server interface for the rich integration.
  It is designed for product embedding and exposes authentication,
  conversations, approvals, and streamed agent events. Use `codex exec --json`
  only for bounded automation tests or as a deliberately reduced fallback,
  not as the long-term rich-client contract.
- **OpenCode:** prefer its ACP server when the installed version supports it.
  The adapter may use `opencode run --format json` as a version-gated fallback
  for basic execution and native session continuation, while clearly marking
  any missing interactive capabilities.
- **Generic command:** support an executable, fixed argument template, working
  directory, stdin prompt option, stdout/stderr, exit code, timeout, and
  cancellation. Its baseline capability is text output only. Rich tool or
  approval events require ACP or a reviewed adapter; SwiftAgent must not guess
  them from arbitrary terminal text.

## The ergonomic experience

### First launch: “Your agents” instead of one settings form

Auto-detect supported local agents and show one card per integration:

- installed / missing / incompatible;
- detected path and version;
- authenticated / action required / unknown;
- native safety capabilities;
- SwiftAgent strict-isolation support;
- supported features such as resume, approvals, attachments, and usage; and
- one official installation or authentication action when needed.

Probes must be read-only, time-bounded, cacheable, and manually refreshable.
Do not run a paid model request merely to determine whether an agent exists.

The user selects a default agent globally or per workspace, but can change it
for each new task.

### Task composer: powerful without becoming a cockpit

The default composer shows:

1. agent selector with readiness state;
2. workspace-relative directory selector;
3. prompt;
4. clear mode/safety summary; and
5. Run.

An expandable “Run options” area exposes only adapter-supported model, mode,
reasoning/effort, attachments, and permission options. Remember choices per
workspace and agent, not as one global configuration.

Switching agents immediately recalculates the controls. If a draft uses a
feature unsupported by the new agent, keep the draft and ask the user to remove
or change that option before running.

### Execution: one timeline with native depth

- Keep messages, tool activity, plans, approvals, questions, and completion in
  one chronological timeline.
- Show the agent badge, model when known, workspace, elapsed time, and effective
  safety posture in a compact sticky header.
- Group noisy tool output by default while preserving a keyboard-accessible
  detail view and bounded raw event diagnostics.
- Translate agent-specific permission requests into consistent decisions only
  when semantics match. Show the native request and consequences before the
  user approves.
- On disconnect or restart, state whether SwiftAgent can reconnect, resume a
  native session, or only display persisted history.

### History: agent-aware and useful

Filter by agent, workspace, status, date, changed files, and verification state.
Each entry shows its originating agent and whether native resumption is still
available. “Continue with another agent” creates a new session using a reviewed,
redacted handoff summary; it never reuses a foreign native session ID.

## Milestone 0 — decouple the core without regressing Claude Code

**Target:** `v0.3.0`

**Release criterion:** the application core contains no Claude-specific task
logic, while the Claude Code adapter passes the existing behavior and safety
suite.

### 0.1 Freeze the current contract with fixtures

**Status: completed and pushed.**

- Capture redacted Claude Code stream fixtures for text, tool use/results,
  session ID, success, failure, malformed lines, cancellation, and resume.
- Add tests for current engine probe, CLI argument construction, strict
  fail-closed behavior, task persistence, and restart recovery.
- Record the exact supported Claude Code version range instead of assuming all
  `claude` executables emit the same protocol.

### 0.2 Introduce the agent registry and normalized events

**Status: completed and pushed.**

- Add the `AgentAdapter`, `AgentCapabilities`, `AgentStatus`, and normalized
  event schemas.
- Move subprocess ownership and adapter selection behind the task manager.
- Persist `agent_id`, `adapter_id`, adapter version, native session ID, and
  capability snapshot with every run.
- Route resumption through the adapter that created the session.
- Migrate existing task records as `agent_id = claude-code`; never discard
  local history during schema migration.

### 0.3 Convert Claude Code into the first adapter

**Status: completed and pushed.**

- Move discovery, arguments, parser, state paths, and settings out of generic
  core modules.
- Map native messages into normalized events without losing raw diagnostic
  metadata.
- Keep permission and question behavior only where the Claude CLI protocol
  truly exposes it; remove dead generic models or finish their wiring.
- Preserve queue limits, cancellation, process-group cleanup, and sandbox
  failure semantics.

### 0.4 Ship the first agent-aware UI

**Status: completed and pushed.**

- Replace Claude-specific Settings with “Your agents,” workspace defaults, and
  per-agent configuration.
- Add the agent selector and capability-aware options to the task composer.
- Display agent identity and safety layers on execution/history screens.
- Provide clear migration copy for existing users: no new credentials and no
  lost sessions.

**Exit gate for `v0.3.0`**

- All current lint, tests, and production build checks pass.
- Golden fixtures prove parity for supported Claude Code behavior.
- A fake adapter can run through start, events, completion, cancellation, and
  persistence without importing Claude-specific modules.
- Existing SQLite data migrates forward and remains readable.
- The UI renders at least three capability combinations without hard-coded
  agent names.

## Milestone 1 — support Codex, OpenCode, and ACP

**Target:** `v0.4.0`

**Release criterion:** one clean install can detect and complete verified local
runs with Claude Code, Codex, and OpenCode through the same interface.

### 1.1 Build the ACP client adapter

**Status: completed, validated, and pushed.**

- Implement stable ACP initialization, capability negotiation,
  authentication handoff, session create/load, prompt turns, updates,
  permissions, terminal requests, file operations, and cancellation.
- Enforce SwiftAgent workspace containment on ACP client file operations.
- Bound terminal output, validate absolute paths, and reject filesystem access
  outside the selected workspace unless an explicit future policy permits it.
- Add the official ACP schema fixtures and a deterministic fake ACP agent to CI.

### 1.2 Add the Codex adapter

**Status: completed, validated, and pushed.**

- Detect the Codex CLI and supported app-server protocol/version.
- Connect using Codex app-server and map threads/turns, streamed items,
  approvals, errors, and cancellation into SwiftAgent events.
- Reuse Codex's official authentication state; never request or persist the
  user's OpenAI credentials in SwiftAgent.
- Map Codex approval and sandbox settings semantically, with native labels and
  warnings for dangerous bypass combinations.
- Test new turn, resume, rejected approval, tool failure, interrupted stream,
  app-server restart, and unsupported version behavior.

### 1.3 Add the OpenCode adapter

- Prefer `opencode acp` so SwiftAgent exercises its standard client path.
- Version-gate the integration and verify advertised capabilities.
- Provide a reduced native JSON-run fallback only when ACP is unavailable;
  label exactly which resume, approval, plan, tool, or attachment behaviors are
  missing.
- Keep OpenCode's provider/model identifiers inside its adapter and discover
  them through OpenCode rather than a hard-coded global catalog.
- Never enable OpenCode session sharing automatically.

### 1.4 Add the restricted generic command adapter

- Use a reviewed manifest schema with executable path, literal arguments,
  prompt transport, working-directory behavior, timeout, environment allowlist,
  and optional version probe.
- Never invoke through `shell=True` or interpolate a prompt into a shell
  command.
- Support text messages, stderr diagnostics, exit status, timeout, and
  cancellation. Mark resume, tools, approvals, and usage unsupported by
  default.
- Provide a “test adapter” flow against a disposable workspace before an
  adapter can be enabled for real projects.

### 1.5 Publish the compatibility matrix

For every built-in adapter, document:

- tested agent versions and operating systems;
- protocol/transport used;
- authentication probe behavior;
- new session, resume, approvals, tools, attachments, plans, usage, and cancel;
- native safety controls;
- SwiftAgent strict external isolation status; and
- known limitations.

Use **verified**, **partial**, **unsupported**, and **unknown**. Do not use a
single misleading “supported” checkmark.

**Exit gate for `v0.4.0`**

- Each of the three named agents completes the same harmless fixture task and
  produces normalized persisted history.
- Resume and approval tests run only where declared; unsupported controls do
  not appear in the composer.
- Killing any adapter process leaves no task falsely marked as running.
- A malformed or unknown native event cannot crash the server or poison another
  active task.
- Security documentation explains native permissions versus SwiftAgent
  isolation for every adapter.

## Milestone 2 — make every agent run reviewable

**Target:** `v0.5.0`

**Release criterion:** different agents produce one honest, comparable Local
Run Receipt without erasing native detail.

### 2.1 Ship the Local Run Receipt

Persist and display:

- intent, agent, adapter/protocol version, model when reported, workspace,
  native session ID, timestamps, and result;
- native permission/sandbox posture and SwiftAgent isolation as separate
  fields, plus an effective safety summary;
- normalized activity ledger with expandable native details;
- approvals, denials, questions, and plan state where supported;
- Git baseline, initial dirty state, changed files, and post-run diff summary;
- verification evidence with explicit `passed`, `failed`, or `not run`; and
- actions to inspect, resume through the same agent, or create an explicit
  cross-agent handoff.

Do not infer test success from an assistant message. Do not claim equivalent
safety because two agents display the same SwiftAgent mode name.

### 2.2 Add deliberate cross-agent handoff

“Continue with another agent” creates a new run after showing a redaction and
content preview. The handoff can include:

- original intent and user-approved summary;
- changed-file names and bounded diff summary;
- explicit verification results;
- unresolved questions; and
- selected user-authored instructions.

Exclude raw credentials, hidden reasoning, full environment dumps, and native
session IDs. The source session remains intact.

### 2.3 Create a three-agent reproducible demo

Add a fictional `demo-workspace/` and one safe task that can be run with Claude
Code, Codex, or OpenCode. The README and project site should show:

- agent auto-detection;
- switching agents without losing the draft;
- capability-aware controls;
- one approval flow;
- unified timeline and receipt; and
- explicit differences in supported features.

Publish one screenshot plus a short redacted video/GIF. Do not manufacture a
perfect side-by-side benchmark; show the workflow and its boundaries.

## Milestone 3 — make the adapter ecosystem credible

**Target:** `v0.6.0`

**Release criterion:** an external contributor can add and validate an adapter
without editing the application core.

### 3.1 Publish the adapter developer kit

- Version the adapter API independently from the app release.
- Provide a minimal fake agent, contract-test harness, event fixtures, manifest
  schema, security checklist, and example adapter.
- Document capability mapping, authentication boundaries, state directories,
  cancellation, output limits, migration policy, and UI behavior.
- Require a compatibility declaration and test evidence for built-in status.

### 3.2 Define adapter trust levels

Use visible labels:

- **built-in verified:** maintained in the repository and release-tested;
- **community verified:** passes the published contract suite for listed
  versions but is maintained externally;
- **local custom:** configured by the user and not endorsed by SwiftAgent.

Never auto-download and execute adapter code from a marketplace. A future
registry requires signatures, provenance, review ownership, update policy, and
an explicit installation confirmation.

### 3.3 Build the contribution loop

- Seed bounded issues labeled by `core`, `adapter:claude`, `adapter:codex`,
  `adapter:opencode`, `protocol:acp`, `ui`, `security`, and `tests`.
- Make two real adapter-fixture tasks `good first issue` with exact acceptance
  criteria.
- Add a first-adapter walkthrough and a compatibility-report issue form.
- Use GitHub Discussions for installation Q&A and adapter proposals only if the
  maintainer can answer them consistently.
- Credit verified compatibility work in release notes.

## Milestone 4 — distribution and growth based on proof

**Target:** after the three built-in adapters and receipt workflow are stable.

- Choose and verify one tagged installation path; attach checksums, SBOM, and
  provenance where the build system can prove them.
- Publish release notes with an adapter compatibility table and one evaluation
  receipt per verified integration.
- Create focused pages for “Claude Code with a control room,” “Codex with a
  control room,” “OpenCode with a control room,” and “Connect any ACP agent.”
- Keep the main positioning agent-neutral: **one local place to run, inspect,
  approve, resume, and compare coding-agent work**.
- Ask users for redacted compatibility reports and workflow friction, not only
  stars.

## Success scorecard

Collect through reproducible test runs and opt-in feedback. Do not add silent
telemetry.

| Signal | Initial target |
| --- | --- |
| Agent detection | Claude Code, Codex, and OpenCode status understood in under 1 minute |
| First successful run | Any one ready agent completes the fixture in under 10 minutes |
| Agent switching | Draft survives a switch; unsupported options are explained before run |
| Adapter correctness | 100% of declared capabilities have fixtures or integration evidence |
| Review completeness | Every terminal run reports agent, safety layers, Git impact, and verification state |
| Reliability | Adapter crash/restart cannot corrupt another task or leave false live state |
| Extensibility | A sample ACP or community adapter passes the contract suite without core edits |
| External proof | Five redacted real-workflow reports across at least two agents before broad promotion |

## Non-goals for this roadmap

- Building or hosting foundation models.
- Copying agent credentials into SwiftAgent.
- Pretending sessions are portable between unrelated native formats.
- Flattening all permission modes into one unsafe universal switch.
- Supporting an agent based only on a successful process launch.
- Remote multi-user execution without a new authentication, authorization,
  transport-security, and workspace-isolation design.
- Automatic commits, resets, pushes, PR merges, or session sharing.
- An unreviewed adapter marketplace.

## Sequencing and decision gates

| Order | Work | Continue only when |
| --- | --- | --- |
| 1 | Adapter contract, events, registry, and migrations | Claude behavior is preserved and a fake adapter works without Claude imports |
| 2 | Agent-aware setup and composer | Controls render from capabilities rather than agent-name conditionals |
| 3 | ACP, Codex, and OpenCode adapters | Each passes versioned fixtures and the same harmless live task |
| 4 | Local Run Receipt and handoff | Safety, Git impact, and verification remain honest across agents |
| 5 | Adapter SDK and community workflow | An external adapter passes the contract suite without core changes |
| 6 | Launch and distribution | Clean install, demo, compatibility matrix, and release evidence are public |

If a gate fails, fix the adapter boundary, safety semantics, or first-run
experience before adding another agent logo. The goal is not a long integration
list; it is the most trustworthy and ergonomic place to use the agents people
already chose.

## Primary technical references

- [Agent Client Protocol introduction](https://agentclientprotocol.com/get-started/introduction)
  and [protocol overview](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v1/overview.mdx)
  — interoperability, capability negotiation, sessions, updates, permissions,
  and cancellation.
- [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server)
  and [Codex CLI commands](https://learn.chatgpt.com/docs/developer-commands) —
  rich client integration, approvals, sessions, streaming, working directories,
  and sandbox/approval controls.
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference) —
  non-interactive streaming, permissions, models, and session continuation.
- [OpenCode CLI reference](https://dev.opencode.ai/docs/cli/) — ACP server,
  JSON event mode, sessions, models, attachments, and permission behavior.

These references define integration surfaces, not permanent compatibility.
Every SwiftAgent release must publish the exact versions and capabilities it
actually verifies.
