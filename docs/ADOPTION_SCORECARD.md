# Opt-in adoption scorecard

SwiftAgent collects no silent telemetry. Product evidence comes from local
reproducible tests and public reports that users deliberately redact and submit.

| Signal | Target | Current release evidence | External opt-in evidence |
| --- | --- | --- | --- |
| Agent detection | Claude Code, Codex, and OpenCode status understood in under 1 minute | Readiness probes and Settings browser QA pass | 0 reports |
| First successful run | Any ready agent completes the fixture in under 10 minutes | Deterministic adapter evaluations pass | 0 reports |
| Agent switching | Draft survives; unsupported controls are explained before run | Capability-aware composer tests and demo | 0 reports |
| Adapter correctness | Every declared capability has fixture/integration evidence | CI compatibility contract passes | Compatibility reports accepted as filed |
| Review completeness | Every terminal run reports identity, safety, Git impact, and verification | Local Run Receipt tests pass | 0 reports |
| Reliability | Crash/restart cannot corrupt another task or remain falsely live | Lifecycle and malformed-stream tests pass | 0 reports |
| Extensibility | External ACP adapter passes without core edits | Adapter API 1.0 example passes | 0 community adapters |
| External proof | Five redacted workflows across at least two agents | Not replaceable by internal fixtures | **0 / 5** |

The public project site asks for compatibility evidence and workflow friction,
not stars. Broad promotion remains gated on five useful redacted reports across
at least two agents. A report can be negative: a clear installation failure,
unsupported version, or confusing control is valuable evidence.

Submit through the Compatibility report or Workflow friction issue form. Never
include credentials, cookies, private keys, native session IDs, hidden reasoning,
private source, environment dumps, personal paths, or prompts you cannot share.
