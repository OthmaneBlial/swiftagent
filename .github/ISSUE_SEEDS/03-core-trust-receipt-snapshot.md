## Outcome

Preserve the adapter trust label used at run creation in Local Run Receipt
history without rewriting older receipts or confusing trust with safety.

## Acceptance criteria

- A forward-only migration adds bounded trust snapshot fields; existing rows
  remain readable and are explicitly unknown/local legacy evidence.
- New receipts persist the registry trust level and evidence link at task start.
- JSON and Markdown exports show the snapshot under agent provenance, not under
  native or SwiftAgent safety.
- Tests cover built-in, local custom, and legacy receipts plus migration
  idempotence.
- No current task, session, or handoff behavior changes.
- `make lint` and `make test` pass.
