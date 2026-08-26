## Outcome

Route image attachments from the composer to Codex only when the selected
adapter advertises the matching capability, preserving workspace and size
limits.

## Acceptance criteria

- The composer exposes image selection only for a ready agent with compatible
  attachment types and preserves the text draft when switching agents.
- The API validates type, size, count, and selected-workspace containment before
  the Codex adapter receives any path.
- Codex app-server fixture evidence proves the image input mapping; other
  adapters receive no silent attachment fallback.
- Unsupported, oversized, outside-workspace, and cancelled selection paths have
  tests and accessible UI feedback.
- No file bytes or personal paths are added to logs or receipts by default.
- `make lint` and `make test` pass, with browser QA at 320 px and desktop width.
