## Outcome

Add one deterministic ACP question round-trip to the public example adapter so
contributors can see how a native question becomes normalized UI evidence.

## Scope

Only the public fake agent, example manifest/report, normalized event fixture,
contract harness test, and directly related docs.

## Acceptance criteria

- The fake agent asks exactly one deterministic question during its basic run
  and consumes the contract manager's `contract-choice` answer.
- The example declares `questions: true` only after the fixture emits both
  `question.requested` and `question.resolved`.
- `expected-events-v1.json`, the manifest expectations, and the generated
  contract report contain both events.
- A regression test fails if either event or the selected answer disappears.
- The scenario performs no network or provider/model call and contains no
  credential, native session ID, or personal path.
- `make adapter-kit-test`, `make lint`, and `make test` pass.

## Out of scope

New UI design, non-ACP adapters, marketplace installation, or new trust labels.
