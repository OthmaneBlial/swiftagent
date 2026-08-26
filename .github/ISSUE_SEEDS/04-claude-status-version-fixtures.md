## Outcome

Make Claude Code readiness claims reproducible across supported, unknown, and
malformed `--version` output without invoking a model.

## Acceptance criteria

- Deterministic fixtures cover a recognized version, a newer unknown version,
  non-zero exit, timeout, and malformed output.
- The status probe never sends a prompt, reads a conversation, or changes auth.
- Only the exact recognized scope may be compatible; unknown versions stay
  visible and unverified with an actionable detail.
- Diagnostics and version text remain bounded and contain no environment dump.
- Compatibility docs state fixture versus live evidence precisely.
- `make lint` and `make test` pass.
