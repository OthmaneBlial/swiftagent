# Security policy

SwiftAgent executes a local Claude CLI process and can edit files in a configured workspace. Treat it as a developer tool for a trusted local machine.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository. Do not post exploit details, secrets, or proof-of-concept payloads in public issues or discussions.

Include the affected version/commit, realistic impact, reproduction steps, and any proposed mitigation. We will acknowledge reports as soon as practical and coordinate a fix before public disclosure.

## Supported safety posture

- Local loopback binding is the default; remote exposure requires explicit opt-in and an external trusted access layer.
- Strict mode fails closed if `bwrap` is absent or unusable.
- Explicit fallback mode is not OS-isolated and is appropriate only for a trusted local context.
- Workspace file endpoints reject traversal and destructive workspace-root operations, but they cannot make an unsandboxed Claude process safe.

If you believe a credential was committed, revoke or rotate it immediately before reporting it. Do not include the secret in the report.
