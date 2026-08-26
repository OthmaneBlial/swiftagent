# Claude Code stream fixtures

These redacted JSONL fixtures freeze the event shapes SwiftAgent v0.2.x already
accepted before the agent-adapter refactor. They cover initialization/session
identity, assistant text, tool use, tool results, successful and failed terminal
results, malformed lines, unknown events, and top-level errors.

The local historical installation used while freezing this contract is
`@anthropic-ai/claude-code` `0.2.69`. Its executable does not start under the
machine's current Node.js `25.9.0`, so this is parser/argument compatibility
evidence, not a successful live-agent certification. SwiftAgent must publish a
separate live-tested CLI version matrix before claiming a wider supported
version range.

Fixtures are fictional and must never contain real prompts, paths, session IDs,
tool output, or credentials.
