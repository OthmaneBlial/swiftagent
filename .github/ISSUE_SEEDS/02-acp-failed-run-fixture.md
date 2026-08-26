## Outcome

Add a deterministic failed-run scenario to the public Adapter API contract so a
new adapter proves failure isolation as well as success and cancellation.

## Scope

Contract fixture schema/model, example fake agent and manifest, JSON report,
tests, and Adapter SDK documentation.

## Acceptance criteria

- `ContractFixture` accepts a bounded optional failure argv scenario and the
  public JSON schema matches the runtime validation.
- The fake agent has a deterministic failure mode with no network call, sleep
  race, secret, or machine-specific path.
- The harness requires a terminal failed task plus a normalized `run.failed`
  event and records `failure_checked: true` without treating expected failure as
  a failed contract.
- A following normal fixture run still completes, proving one malformed/failed
  run does not poison the adapter registry or database.
- The generated report and docs explain the exact failure evidence.
- `make adapter-kit-test`, `make lint`, and `make test` pass.

## Out of scope

Production crash recovery redesign, remote agents, or changing the existing
success/cancellation meanings.
