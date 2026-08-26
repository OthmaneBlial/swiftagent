# Adapter compatibility report

Copy this template beside a proposed manifest.

## Identity

- Agent name and version:
- Adapter ID and version:
- Adapter API version:
- ACP implementation/library version:
- Maintainer and review owner:

## Test scope

- Operating systems and architectures:
- Installation source and checksum/signature:
- Authentication method (never include credentials):
- State directories:
- Contract-suite command:
- Contract-report or CI artifact:
- Redacted Local Run Receipt:

## Capability evidence

Use only **verified**, **partial**, **unsupported**, or **unknown**.

| Capability | Status | Fixture/evidence | Known boundary |
| --- | --- | --- | --- |
| New session |  |  |  |
| Resume |  |  |  |
| Cancellation |  |  |  |
| Tool events |  |  |  |
| Approvals |  |  |  |
| Questions |  |  |  |
| Plans |  |  |  |
| Usage |  |  |  |
| Models/modes |  |  |  |
| Attachments |  |  |  |
| Native safety |  |  |  |
| SwiftAgent strict isolation |  |  |  |

## Failure behavior

- Malformed frame:
- Unknown event:
- Agent process exit:
- Timeout/output limit:
- Cancellation race:
- Restart recovery:

## Security review

- Completed checklist:
- Forwarded environment names:
- Network requirement:
- Credential/state boundary:
- Remaining risks:

## Compatibility decision

- Proposed trust level: `local custom` or `community verified`
- Exact versions covered:
- Re-test trigger:
- Reviewer/date:
