# ACP v1 adapter

SwiftAgent can run a local coding agent that implements the stable Agent Client
Protocol over JSON-RPC 2.0 on standard input/output. The implementation uses
the official Python SDK and currently targets protocol version 1, tested
against stable schema release `schema-v1.21.0`.

## Configure a local agent

Set a literal JSON argument array. SwiftAgent never invokes a shell and never
interpolates the task prompt into a command string.

```sh
export SWIFTAGENT_ACP_COMMAND_JSON='["your-agent", "acp"]'
```

The same value can be saved from **Settings → ACP adapter options**. Keep the
executable as the first item and each argument as a separate JSON string.
Credentials remain in the agent's official authentication state; SwiftAgent
does not request or persist provider secrets.

## Safety boundary

- ACP file paths must be absolute and resolve inside the selected task
  workspace.
- File reads and writes are limited to 1 MiB per call.
- Terminal commands are literal executable/argument arrays, never shell text.
- At most eight terminals can exist per session and retained output is capped
  at 1 MiB.
- Strict isolation uses Bubblewrap and fails closed when unavailable. Fallback
  mode must be selected explicitly and is reported as not OS-isolated.
- Remote ACP transports are not supported.

## Capability mapping

SwiftAgent negotiates capabilities during `initialize` and persists the
effective snapshot with the run. Session load/resume and prompt attachment
types appear only when the agent advertises them. ACP message, thought, tool,
plan, permission, usage, and completion updates are converted to normalized
SwiftAgent events while bounded native metadata remains available for
diagnostics.

Terminal authentication is deliberately not advertised. If an agent requires
it, SwiftAgent asks the user to complete the agent's official login command in
a terminal and retry.
