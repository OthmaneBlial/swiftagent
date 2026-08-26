## Outcome

Keep readiness, adapter trust, authentication, and isolation understandable on
narrow screens without relying on color or hover.

## Acceptance criteria

- At 320 px, every agent card shows a readable trust label with no horizontal
  document overflow or clipped default action.
- Built-in, community, and local-custom meanings are available to keyboard,
  touch, and screen-reader users without requiring `title` hover text.
- Trust evidence links have distinct accessible names and visible focus.
- A visual/browser regression covers one card per trust level and one missing
  legacy trust field.
- The copy keeps trust separate from installed, auth, native safety, and active
  SwiftAgent isolation.
- `npm --prefix client run lint` and `npm --prefix client run build` pass.
