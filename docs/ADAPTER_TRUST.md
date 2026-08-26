# Adapter trust policy

SwiftAgent shows adapter provenance separately from readiness, authentication,
capabilities, native safety, and external isolation. A trust label answers who
maintains and release-tests the translation layer. It does not certify an
agent's output or make a command safe to run.

## Levels

| Label | Assignment | Evidence and boundary |
| --- | --- | --- |
| **Built-in verified** | Adapter code is maintained in this repository. | The release suite covers its adapter contract and the linked compatibility matrix states exact live or fixture scope. |
| **Community verified** | Adapter is maintained externally and reviewed by a SwiftAgent maintainer. | A passing public contract report, exact adapter and agent versions, OS scope, security checklist, distribution origin, and named review owner are required. The label covers only that evidence. |
| **Local custom** | A user places a manifest on their machine. | SwiftAgent validates and loads the local configuration but does not endorse its executable, compatibility declaration, maintainer, or behavior. |

Verified levels require a maintainer-assigned evidence link in the in-repository
registry definition. Adapter API manifests have no trust field and cannot
self-promote. Even a passing contract declaration remains **local custom** until
an external review is accepted and represented by repository-owned metadata.

## Installation and execution policy

SwiftAgent never searches for, downloads, installs, updates, or automatically
executes adapter code from a catalog. A user separately installs an agent and
places a reviewed `*.adapter.json` file in the local adapter directory. The
server loads direct files only at startup, shows skipped manifests, and rejects
collisions with registered IDs.

Changing a label does not bypass the normal execution boundary. Literal argv,
bounded environment forwarding, workspace checks, cancellation, output limits,
and the selected isolation policy still apply. A built-in adapter can drive an
unavailable or unauthenticated agent; a local custom adapter can still pass its
contract fixture. Those are different facts and remain visibly separate.

## Gate for any future registry

A downloadable registry must not ship until all of these are implemented and
reviewed:

- signed index metadata and signed, immutable release artifacts;
- verifiable source and build provenance plus published checksums;
- one named maintainer and one SwiftAgent review owner per entry;
- exact compatibility scope, contract artifacts, and re-test triggers;
- a documented security response, revocation, and update policy;
- a preview of executable, version, origin, permissions, environment names, and
  state directories before installation;
- explicit user confirmation for the exact pinned artifact and every update;
- no silent install, trust promotion, background update, or execution; and
- an audit record that distinguishes registry metadata, local installation,
  runtime readiness, and the active safety layers.

Until that complete gate exists, documentation and issue proposals are the only
discovery mechanism. Users remain in control of every local installation.
