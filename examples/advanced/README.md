# Resume a Claude session

After a completed task exposes a session ID, continue it without repeating its entire context:

```bash
python3 resume_session.py <session-id> "Now make the smallest safe implementation change"
```

Run this against a local SwiftAgent server. It exits `0` on a completed resumed task and `1` on failure.
