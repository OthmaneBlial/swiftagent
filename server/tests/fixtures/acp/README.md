# ACP protocol fixture

This fixture targets ACP protocol version 1 and the stable
[`schema-v1.21.0`](https://github.com/agentclientprotocol/agent-client-protocol/releases/tag/schema-v1.21.0)
release. `fake_agent.py` uses the official Python SDK on both sides of the
stdio connection so schema changes fail the contract tests instead of being
silently accepted by a hand-written parser.

The fake agent deterministically exercises initialization, capability
negotiation, new/load session, streamed messages, tool and plan updates,
permission selection, workspace-scoped file access, bounded terminal output,
usage, completion, and cancellation.
