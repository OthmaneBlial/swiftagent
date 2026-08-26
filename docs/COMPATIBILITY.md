# Adapter compatibility matrix

Last verified: 2026-08-27 for SwiftAgent v0.6.0.

The words in this matrix are evidence levels, not marketing labels:

- **verified** — covered by a deterministic end-to-end adapter contract in CI;
  live probes are named explicitly and never imply that a paid model call ran;
- **partial** — a native or backend path exists, but negotiation, UI routing,
  platform coverage, or end-to-end proof is incomplete;
- **unsupported** — SwiftAgent deliberately does not expose the capability; and
- **unknown** — the current evidence cannot make an honest claim.

Codex and OpenCode were additionally initialized against the installed macOS
CLIs without sending a model prompt. Claude Code's exact local CLI contract is
unknown because its live version probe failed; its row is fixture-backed only.

## Identity, transport, and trust

| Adapter | Tested contract / OS | Transport | Authentication probe | Native safety | SwiftAgent strict isolation |
| --- | --- | --- | --- | --- | --- |
| Claude Code | stream-json fixture 2.1.52 on macOS arm64; exact live CLI **unknown** | `stream-json` subprocess | **unknown** — executable/version only | **partial** — native permission mode is passed through, interactive approvals are not normalized | **partial** — Bubblewrap fail-closed path is implemented for Linux; macOS has no verified strict backend |
| ACP Agent | protocol 1, schema v1.21.0, Python SDK 0.12.x fixture | ACP v1 JSON-RPC over stdio | **partial** — negotiated methods; terminal login stays outside SwiftAgent | **partial** — permission choices are native-agent-defined | **partial** — same Linux Bubblewrap limitation |
| Codex | CLI 0.149.1 on macOS arm64 plus deterministic app-server fixture | bidirectional app-server v2 JSONL | **verified** — free `codex login status`, credentials never copied | **verified** — approval/sandbox labels and dangerous combination guard are contract-tested | **partial** — native Codex sandbox is separate; external strict backend remains Linux-only |
| OpenCode | CLI 1.18.13 on macOS arm64 plus ACP/JSON fixtures | ACP v1; reduced `run --format json` fallback | **partial** — models prove a usable catalog, provider execution is not probed | **partial** — ACP permissions are mapped; JSON fallback has none | **partial** — same Linux Bubblewrap limitation |
| Generic command | manifest v1, fixture 1.0.0 on macOS arm64 | literal argv subprocess | **unsupported** — owned entirely by the command | **unsupported** | **partial** — disposable preflight plus Linux Bubblewrap when available; fallback is unisolated |

## Run capabilities

| Adapter | New run | Resume | Fork | Approvals | Tools | Attachments | Plans | Usage | Cancel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Code | **verified** | **verified** | **unsupported** | **unsupported** | **verified** | **unsupported** | **unsupported** | **unsupported** | **verified** |
| ACP Agent | **verified** | **partial** — negotiated per agent | **unknown** — native negotiation retained, no SwiftAgent control | **verified** | **verified** | **unsupported** — native types retained but not routed yet | **verified** | **verified** | **verified** |
| Codex | **verified** | **verified** | **partial** — native support known, no SwiftAgent fork control yet | **verified** | **verified** | **partial** — image backend exists, composer routing is pending | **verified** | **verified** | **verified** |
| OpenCode | **verified** | **verified** | **partial** — native ACP support known, no SwiftAgent fork control yet | **verified** through ACP; JSON fallback **unsupported** | **verified** | **partial** — native/JSON paths exist, composer routing is pending | **verified** through ACP; JSON fallback **unsupported** | **verified** | **verified** |
| Generic command | **verified** | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **unsupported** | **verified** |

The machine-readable source used by CI is
[`server/tests/fixtures/compatibility-v0.6.json`](../server/tests/fixtures/compatibility-v0.6.json).
CI rejects missing adapters, unknown status words, a **verified** feature absent
from the registry, or an **unsupported** feature still declared to the UI.

## Shared v0.6 acceptance evidence

- Claude Code, Codex, and OpenCode complete the same harmless, no-network prompt
  through their own deterministic transports and persist assistant history plus
  normalized terminal events.
- Resume and approvals run only in adapter tests that declare them.
- Claude, ACP, Codex, OpenCode JSON, and generic-command cancellation paths end
  in a terminal persisted state and clean up their subprocess groups.
- Malformed Claude, Codex, and OpenCode JSON streams are isolated to their task;
  unknown Codex notifications are ignored safely.
- Generic commands remain disabled until an exact manifest/executable pair
  passes a disposable-workspace marker test.

## Known limitations

- “Partial isolation” is not a sandbox guarantee. On systems without usable
  Bubblewrap, explicit fallback mode gives the agent the local user's access.
- Native provider permissions and SwiftAgent external isolation are independent
  layers. Enabling one does not imply the other.
- Model catalogs are adapter- and workspace-owned; SwiftAgent does not maintain
  a universal model list.
- Attachments and explicit session fork controls remain milestone 2 work and are
  not advertised merely because a native protocol announced them.
- Remote agents, shared sessions, multi-user authentication, and hosted control
  planes remain out of scope for v0.6.
