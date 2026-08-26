# Codex app-server implementation research plan

## Main question

What stable, locally verifiable Codex app-server v2 lifecycle and safety
semantics must SwiftAgent implement for a rich native adapter?

## Subtopics

1. Official stdio transport, initialize handshake, thread/turn lifecycle, and
   cancellation.
2. Account-state reuse, model discovery, server-initiated approvals, event
   mapping, errors, and process cleanup.
3. Native approval/sandbox policy versus SwiftAgent's external process
   isolation, including dangerous bypass combinations.
4. Generated schema fixtures and deterministic tests for success, resume,
   approval denial, tool failure, interruption, malformed frames, and
   unsupported versions.
