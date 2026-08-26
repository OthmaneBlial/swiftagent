# Restricted generic command adapter

The generic adapter is an escape hatch for local text agents that do not expose
ACP or a reviewed native protocol. It intentionally supports less than the
built-in Claude Code, Codex, and OpenCode integrations.

## Activation contract

Paste a schema-v1 manifest into **Your agents → Generic command adapter** and
run the disposable test. Saving any semantic manifest change clears the test
receipt and disables the adapter. Replacing or modifying the executable also
invalidates the receipt.

```json
{
  "schema_version": 1,
  "name": "My text agent",
  "executable": "/absolute/path/to/agent",
  "arguments": ["run", "--plain"],
  "prompt_transport": "stdin",
  "cwd_mode": "task",
  "timeout_seconds": 300,
  "environment_allowlist": ["PATH", "LANG"],
  "max_output_bytes": 1048576,
  "version_probe": {
    "arguments": ["--version"],
    "expected_output_prefix": "my-agent 1.",
    "timeout_seconds": 5
  }
}
```

The test runs the exact executable and fixed arguments in a temporary directory,
sends a unique marker through the selected prompt transport, requires that
marker on stdout, applies the optional version probe, and records the executable
identity. The temporary directory is removed after the test.

## Hard boundaries

- `subprocess_exec` receives a literal argument array; there is no shell.
- A prompt is either raw UTF-8 stdin or one final, separate argument. It is
  never interpolated into an existing argument.
- Only named environment variables are inherited.
- Stdout, stderr, arguments, timeout, and version output are bounded.
- The subprocess runs in the selected task directory or workspace root.
- Strict mode requires usable Bubblewrap. Fallback mode is explicitly
  unisolated and the UI warns that a disposable cwd is not a security sandbox.
- Cancellation and timeout terminate the process group.

The adapter exposes text, stderr diagnostics, exit status, timeout, and
cancellation. Resume, fork, tool events, approvals, questions, plans,
attachments, model discovery, and usage are always unsupported. SwiftAgent does
not infer rich events from terminal text.
