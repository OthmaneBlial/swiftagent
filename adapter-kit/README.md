# SwiftAgent Adapter Kit

This kit lets an external contributor connect a local ACP v1 agent without
editing SwiftAgent's application core. The extension boundary is out of process:
SwiftAgent validates a JSON manifest, launches a literal command array, and
speaks ACP over stdio. It never imports third-party adapter code into the server.

Current adapter API: **1.0**

Contract suite: **`swiftagent-adapter-contract-v1`**

## Try the example

```bash
make adapter-kit-test
```

Or run the receipt-producing harness directly:

```bash
PYTHONPATH=server server/.venv/bin/python \
  -m swiftagent.adapter_sdk.contract \
  --manifest adapter-kit/example-adapter/example-acp.adapter.json
```

The example exercises a new session, a resumed session, workspace file
callbacks, one approval, tool events, a plan, usage, a terminal result,
cancellation, and a deterministic failed run that still leaves the harness able
to complete a following normal run. Everything runs in a temporary workspace
with no network call. The contract report records `failure_checked: true` and
`failure_event_types` (including `run.failed`) when a fail fixture is supplied;
expected failure is evidence, not a failed contract.

## Add a local adapter

1. Copy `example-adapter/example-acp.adapter.json` and the JSON schema. Local
   manifests must end in `.adapter.json`; evidence JSON beside them is ignored.
2. Implement ACP v1 in your executable.
3. Declare only capabilities your fixture can prove.
4. Run the contract harness and save its JSON report.
5. Complete `SECURITY_CHECKLIST.md` and `COMPATIBILITY_REPORT.md`.
6. Put the reviewed manifest and its local executable beside each other in:

   ```text
   ~/.swiftagent/adapters/
   ```

   When `SWIFTAGENT_DATA_DIR` is set, the default becomes
   `$SWIFTAGENT_DATA_DIR/adapters/`. Override it explicitly with
   `SWIFTAGENT_ADAPTER_DIR`.
7. Restart SwiftAgent and inspect **Your agents**. Invalid manifests are skipped
   and reported; they cannot replace a built-in agent ID.

Only direct `*.adapter.json` children are loaded. SwiftAgent does not search the
internet, clone a repository, install a package, or update the command.

## Manifest tokens

Two exact local tokens are supported inside literal command arguments:

- `${manifest_dir}` — directory containing the reviewed manifest;
- `${python}` — the Python interpreter running SwiftAgent, useful for the
  dependency-free example.

There is no shell interpolation, prompt interpolation, glob expansion, or
command substitution.

See [the full developer guide](../docs/ADAPTER_SDK.md), the
[manifest schema](schema/adapter-manifest-v1.schema.json), the
[normalized event fixture](fixtures/expected-events-v1.json), and the
[security checklist](SECURITY_CHECKLIST.md).
