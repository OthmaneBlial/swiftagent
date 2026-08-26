# Deliberate cross-agent handoffs

SwiftAgent does not pretend that Claude Code, Codex, OpenCode, ACP agents, and
custom commands share a native session format. “Continue with another agent”
creates a separate run in the same reviewed workspace after a two-step local
handoff.

## Review before execution

1. Open a terminal run's Local Run Receipt and choose **Continue with another
   agent**.
2. Select the target agent and the bounded context fields to include.
3. Edit and explicitly approve the summary. Optional additional instructions
   must be authored by the user.
4. Generate the redacted preview. SwiftAgent stores only the sanitized preview,
   its redaction report, and the fields excluded by design.
5. Read the exact prompt, then start the new run. A preview expires after 30
   minutes and can be consumed only once.

Changing any selection or editable text requires generating a fresh preview.
The source task, its receipt, and its native session remain unchanged. The new
receipt links back to the source run ID, never to a native session ID.

## Transferable context

The user can select:

- original user intent;
- an editable, explicitly approved summary;
- net changed-file names, without file contents;
- the bounded final Git diff stat;
- explicit `passed`, `failed`, or `not_run` verification evidence;
- questions that were requested but not answered; and
- additional user-authored instructions.

Answered questions are not copied. Agent messages, reasoning events, tool
output, and native metadata are not handoff inputs.

## Always excluded

- Native session IDs and native session state.
- Hidden reasoning or thought events.
- Native event metadata, full tool output, and full environment dumps.
- File contents and raw credentials detected by the redaction boundary.

The redactor covers common API/token formats, private keys, bearer values,
secret-like assignments, URL credentials, native session IDs, environment
blocks, and common sensitive filenames such as `.env` and private keys. This is
defense in depth, not a guarantee that arbitrary prose contains no secret. The
exact sanitized prompt is deliberately the final approval surface.

## Local persistence and API

```text
POST /api/tasks/{source_run_id}/handoff/preview
POST /api/handoffs/{preview_id}/start
```

`run_handoffs` stores sanitized content, the exact prompt, the redaction report,
expiry, single-use state, source run ID, and eventual target run ID. Raw preview
input is not persisted. Replaying or starting an expired preview fails closed.
