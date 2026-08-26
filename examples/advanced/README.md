# Resume a native agent session

After a completed task exposes a resumable native session ID, continue it
through the same adapter without repeating its entire context:

```bash
python3 resume_session.py <session-id> "Now make the smallest safe implementation change"
```

Run this against a local SwiftAgent server. It exits `0` on a completed resumed task and `1` on failure.
SwiftAgent looks up the source run and infers its original agent. Use
`--agent <id>` only when the source receipt is unavailable; cross-agent work
must use the reviewed handoff flow instead.
