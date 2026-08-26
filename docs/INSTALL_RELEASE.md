# Install a verified tagged release

The supported tagged path uses the GitHub release bundle. It includes a prebuilt
client, so runtime installation needs Python 3.11+ and `make`, not Node.js.

## Download and verify v0.6.0

```bash
mkdir swiftagent-v0.6.0-download
cd swiftagent-v0.6.0-download
gh release download v0.6.0 \
  --repo OthmaneBlial/swiftagent \
  --pattern 'swiftagent-v0.6.0.tar.gz' \
  --pattern 'SHA256SUMS'
shasum -a 256 -c SHA256SUMS --ignore-missing
gh attestation verify swiftagent-v0.6.0.tar.gz \
  --repo OthmaneBlial/swiftagent
```

The checksum command must report `swiftagent-v0.6.0.tar.gz: OK`. The attestation
must identify `OthmaneBlial/swiftagent` and the expected GitHub Actions workflow.
Download `swiftagent-v0.6.0.spdx.json` as well when auditing dependencies; the
release workflow also creates an SBOM attestation for the archive.

## Install and start

```bash
tar -xzf swiftagent-v0.6.0.tar.gz
cd swiftagent-v0.6.0
make install-release
make start-release
```

Open `http://127.0.0.1:8000`, inspect **Your agents**, and select a dedicated
workspace before the first real task. Authentication remains in each agent's
own CLI. SwiftAgent does not ask for provider credentials.

`make install-release` creates `server/.venv` and installs runtime dependencies
from declared package metadata. `make start-release` serves the bundled React
client through FastAPI without rebuilding it. For development or source changes,
use the normal clone plus `make setup` path instead.

## Evidence assets

The release also publishes five `*-evaluation.json` receipts. They prove the
tag's deterministic adapter fixtures only. Read their `boundary` fields and the
compatibility matrix before treating a local CLI version as supported.
