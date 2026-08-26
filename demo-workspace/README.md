# Northstar Release Desk demo

This fictional, dependency-free workspace is the public SwiftAgent demo fixture.
It contains no credentials, network calls, generated data, or personal paths.

The same bounded task can be prepared for Claude Code, Codex, or OpenCode:

```bash
server/.venv/bin/python scripts/demo_workspace.py prepare claude-code
server/.venv/bin/python scripts/demo_workspace.py prepare codex
server/.venv/bin/python scripts/demo_workspace.py prepare opencode
```

Each command creates a separate Git repository under `demo-workspace/runs/` so
one agent cannot inherit another agent's edits or native session. In SwiftAgent,
set the workspace root to this repository and use the matching directory:

```text
demo-workspace/runs/claude-code
demo-workspace/runs/codex
demo-workspace/runs/opencode
```

Copy `TASK.md` from that prepared directory into the composer. Keep native
approval controls enabled where the selected adapter exposes them. An adapter
without approval support must display that limitation instead of simulating an
approval.

Validate the fixture itself without calling an agent:

```bash
server/.venv/bin/python scripts/demo_workspace.py verify
```

The verifier proves that the baseline fails the stated acceptance test and the
reference implementation passes it. It does not claim that a live provider,
authentication state, model, or operating system was tested.
