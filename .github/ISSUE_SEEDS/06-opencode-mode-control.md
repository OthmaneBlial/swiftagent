## Outcome

Expose OpenCode modes discovered through ACP without hard-coding provider names
or showing the control for the reduced JSON fallback.

## Acceptance criteria

- The ACP status/negotiation fixture returns at least two deterministic modes.
- The composer shows a mode control only when `mode_discovery` is negotiated and
  preserves a valid selection while switching tasks.
- The chosen mode is sent through the documented ACP method and persisted as
  bounded run configuration evidence.
- Native JSON fallback and agents without mode discovery show no inert control.
- Unknown/removed modes fall back visibly without changing the agent or model.
- `make lint` and `make test` pass, including accessible keyboard interaction.
