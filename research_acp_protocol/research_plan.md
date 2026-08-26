# ACP implementation research plan

## Main question

What exact stable Agent Client Protocol transport, methods, capabilities, and
message shapes must SwiftAgent implement for a safe local ACP client adapter?

## Subtopics

1. Official protocol lifecycle and schemas: initialization, sessions, prompts,
   updates, permissions, cancellation, and authentication.
2. Official client callbacks: workspace-contained file operations and bounded
   terminal creation/output/wait/release behavior.
3. Conformance evidence: official schema/examples and the minimum deterministic
   fake agent needed to test negotiation, a prompt turn, permission handling,
   file containment, terminal bounds, malformed messages, and cancellation.

## Synthesis

Implement only stable official fields, preserve unknown fields as bounded
diagnostics, reject unsafe paths before any client callback, and encode the
researched contract in local fixtures and deterministic tests.
