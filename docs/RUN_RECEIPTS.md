# Local Run Receipts

SwiftAgent stores one versioned Local Run Receipt for every run created from
schema v4 onward. The receipt is evidence for review; it is not an agent score
and it does not make different agents' safety models equivalent.

## What is persisted

- The user-authored intent, selected agent, adapter and protocol versions,
  reported model, workspace, native session ID, timestamps, and terminal result.
- Every normalized adapter event in order, with its normalized payload and the
  bounded native event type and metadata retained for inspection.
- Approval requests and outcomes, questions, latest plan, latest usage, and tool
  counts when the adapter exposes them.
- A Git snapshot before process start and after termination: baseline commit,
  initial dirty paths, net paths changed during the run, and the final worktree
  diff summary.
- Native agent controls and SwiftAgent OS isolation as distinct layers. The
  effective summary says when fallback mode means no OS isolation.
- Explicit verification evidence. Its default is `not_run`; SwiftAgent never
  converts assistant prose into a passing test result.

Historical tasks created before schema v4 get an honest partial receipt. Their
Git capture is marked unavailable and verification remains `not_run`; SwiftAgent
does not inspect today's working tree and present it as historical evidence.

## API and exports

```text
GET /api/tasks/{run_id}/receipt
PUT /api/tasks/{run_id}/receipt/verification
GET /api/tasks/{run_id}/receipt/export?format=json
GET /api/tasks/{run_id}/receipt/export?format=markdown
```

`passed` and `failed` verification updates require a user-authored evidence
summary and can optionally record the command. `not_run` is always available.
JSON export contains the complete receipt returned to the UI, including native
event details. Markdown is a compact, redaction-friendly review summary.

## Git evidence boundaries

The baseline and final snapshots describe the selected repository and preserve
its initial dirty state. `changed_files` is the net path-level difference across
the run, including dirty files modified again, new untracked files, removals,
renames, and commits made during the run. A file changed and then restored to its
baseline content is correctly absent from the net list.

The receipt does not claim which process or person made a change while the run
was active. Concurrent edits share the same local worktree and therefore appear
in the evidence. This is a review signal, not process attribution.

## Safety interpretation

Native permissions and sandboxing belong to the selected coding agent.
SwiftAgent isolation is a separate wrapper around the process. The receipt
records both even if one layer is unavailable. In particular, `fallback` means
that SwiftAgent did not apply OS-level isolation; a native agent sandbox, when
reported, is still shown independently.
