# Codex app-server adapter

SwiftAgent integrates Codex through the official `codex app-server` interface,
the same rich-client boundary used for authentication, conversation history,
approvals, and streamed agent events. The initial compatibility fixture is
generated from `codex-cli 0.149.1` and app-server protocol v2.

## Readiness

Install Codex and complete its official login flow:

```sh
codex login
codex login status
```

SwiftAgent runs only free local readiness commands (`--version`, `app-server
--help`, and `login status`) during detection. It never asks for, copies, or
stores an OpenAI API key or ChatGPT token. At run start, `account/read` confirms
that app-server can reuse the active Codex account.

Set `SWIFTAGENT_CODEX_PATH` or use **Settings → Codex adapter options** only
when `codex` is not on `PATH`.

## Native and SwiftAgent safety

The default native profile is:

- approval policy: `on-request`;
- approvals reviewer: `user`;
- sandbox: `workspace-write`;
- network access: disabled by the turn sandbox policy.

SwiftAgent reports native Codex safety separately from its process isolation.
Strict mode adds Bubblewrap containment and fails closed when Bubblewrap is
unavailable. Fallback mode has no outer OS isolation and relies on Codex's
native sandbox.

`never` plus `danger-full-access` disables both native Codex layers. SwiftAgent
rejects that combination until the user explicitly checks the dangerous-bypass
confirmation. The warning is especially important in fallback mode, where the
process otherwise inherits the local user's access.

## Protocol behavior

Each run owns one local stdio app-server process:

1. `initialize`, then `initialized`;
2. `account/read` and bounded `model/list` discovery;
3. `thread/start` or `thread/resume`;
4. `turn/start`, streamed `item/*`, plan, usage, warning, and error events;
5. native server-initiated command, file, or permission approval requests;
6. `turn/completed`, or `turn/interrupt` during cancellation.

Unknown notifications are ignored safely with debug diagnostics. Frames,
pending requests, stderr, native metadata, model catalogs, and shutdown grace
are bounded. A malformed or interrupted stream fails only its own task and the
process group is terminated.

The current adapter accepts image attachments that resolve inside the selected
workspace. Rich attachment controls and picker-backed model discovery remain
capability-driven; a model ID is never assumed to work across other agents.

Official reference: [Codex app-server documentation](https://learn.chatgpt.com/docs/app-server).
