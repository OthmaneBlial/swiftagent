# Adapter security checklist

Complete this for every compatibility report. A passing contract is necessary,
not a security endorsement.

## Process and distribution

- [ ] The manifest uses an argv array and no shell executable or wrapper.
- [ ] Installation is a separate, explicit user action; SwiftAgent does not
      download or update the adapter.
- [ ] The executable origin, version, checksum/signature when available, and
      maintainer are documented.
- [ ] Cancellation terminates the agent process tree and persists a terminal
      run state.
- [ ] Stdout is reserved for bounded ACP frames; diagnostics go to bounded
      stderr.

## Credentials and state

- [ ] Authentication is completed in the agent's own CLI before SwiftAgent is
      started.
- [ ] The adapter never asks SwiftAgent to store a provider credential.
- [ ] Every forwarded environment variable is named in
      `environment_allowlist`; credential variables are justified explicitly.
- [ ] State directories are documented. The manifest does not make them
      writable or bypass strict isolation automatically.
- [ ] Logs, events, fixtures, compatibility reports, and screenshots contain
      no token, cookie, private key, native session ID, or personal path.

## Workspace and protocol

- [ ] ACP file callbacks use absolute paths inside the selected workspace.
- [ ] Terminal commands use literal arguments and bounded output.
- [ ] The agent does not claim file, terminal, approval, question, plan, usage,
      model, attachment, resume, or sandbox support without fixture evidence.
- [ ] Unknown and malformed native messages fail only the current task.
- [ ] Strict SwiftAgent isolation and native agent safety are reported as
      separate layers.

## Evidence

- [ ] The public contract harness passes from a clean checkout.
- [ ] The exact agent version and operating systems are listed.
- [ ] New-session, declared capability, resume, cancellation, failure, and
      output-limit behavior have evidence or are marked unsupported/unknown.
- [ ] The compatibility report links redacted receipts or CI artifacts.
- [ ] A maintainer is identified for future compatibility regressions.
