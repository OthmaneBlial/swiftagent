# Basic task stream

Start SwiftAgent first (`make dev` or `make start`), then run:

```bash
python3 start_task.py "List the top-level files and explain this project in two sentences"
python3 start_task.py --agent codex "List the top-level files and explain this project in two sentences"
```

Without `--agent`, the server uses the default selected during onboarding or in
**Your agents**. The script exits `0` for a completed task and `1` when the
server reports failure. It uses the local WebSocket protocol and requires the
`websockets` package installed by `make setup`.
