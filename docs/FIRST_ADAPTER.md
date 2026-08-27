# Your first SwiftAgent adapter

This walkthrough connects one already-installed ACP v1 coding agent without
editing SwiftAgent core. It produces local evidence first; it does not download
software or grant a trust label.

## 1. Establish a clean baseline

From a fresh checkout:

```bash
make setup
make adapter-kit-test
```

The example must finish with `"result": "passed"`, `resume_checked: true`,
`cancellation_checked: true`, and `failure_checked: true` (plus
`failure_recovery_checked: true` when a fail fixture is present). If it does
not, fix the checkout before changing the fixture.

## 2. Copy and reduce the example

Copy `adapter-kit/example-adapter/` outside the tracked example. Rename the
manifest so it still ends in `.adapter.json`, then change all of these fields:

- `agent_id`, `display_name`, `adapter_id`, and `adapter_version`;
- the literal `command` array and free `version_probe`;
- exact tested versions, systems, evidence names, and date; and
- documentation and installation URLs.

Start every capability as false or unknown. Enable it only after the fake or
live fixture proves its normalized evidence. Do not infer support from marketing
documentation or from another version.

## 3. Document the boundary

Authenticate with the agent's own CLI. Record its state directories, but do not
add broad writable home-directory mounts. Forward an environment variable only
when unavoidable and name it explicitly in both `environment_allowlist` and the
compatibility report. Never put a provider key, cookie, native session ID,
personal path, private prompt, or environment dump in a fixture.

The command is literal argv. Shells, command substitution, glob expansion,
remote installers, and background update commands do not belong in a manifest.

## 4. Build deterministic evidence

Keep a network-free fixture mode that can prove the declared events. Then run:

```bash
PYTHONPATH=server server/.venv/bin/python \
  -m swiftagent.adapter_sdk.contract \
  --manifest path/to/your-agent.adapter.json \
  --output path/to/contract-report.json
```

Test at least a new session, every declared event capability, resume when
declared, cancellation, deterministic failure (`run.failed` plus a following
successful run), malformed output, process exit, timeout, and output limits.
Unsupported behavior must remain explicit rather than simulated.

## 5. Review locally

Copy only the reviewed manifest and executable into
`~/.swiftagent/adapters/`, restart SwiftAgent, and open **Your agents**. Confirm:

- the card says **Local custom** even when the contract passes;
- the installed version and compatibility scope are accurate;
- unavailable controls stay hidden or disabled;
- auth, native safety, and SwiftAgent isolation remain separate facts;
- invalid sibling manifests are skipped with a bounded warning; and
- one real run yields a redacted Local Run Receipt and cancels cleanly.

Remove the local files after the review if they were only a fixture.

## 6. Propose review

Open an Adapter proposal first. When the scope is accepted, submit the
Compatibility report issue form with:

- the completed `adapter-kit/SECURITY_CHECKLIST.md`;
- exact versions and operating systems;
- executable origin and checksum/signature evidence;
- the generated contract report and a redacted Local Run Receipt;
- failure and limit evidence; and
- a named external maintainer and re-test trigger.

A passing report remains **Local custom**. **Community verified** requires a
SwiftAgent maintainer to review the evidence and add repository-owned trust
metadata for the exact supported scope.
