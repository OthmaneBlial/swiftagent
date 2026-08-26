# Release and compatibility credits

Every release is evidence-first. A tag or generated changelog does not expand
the compatibility claims in `docs/COMPATIBILITY.md`.

Before publishing a release:

1. Run `make lint`, `make test`, `make adapter-kit-test`, and `make demo-verify`.
2. Verify the compatibility matrix still covers every built-in registry entry.
3. Re-test each version newly described as verified and link its redacted
   contract report or Local Run Receipt.
4. List adapter trust changes separately from readiness, capability, or sandbox
   changes.
5. Use the generated release-note category for adapter and protocol work.
6. Under **Compatibility credits**, name each external contributor whose
   report, fixture, reproduction, or review changed a compatibility claim, link
   the accepted issue or pull request, and state the exact adapter/agent scope.
7. Call out unverified, partial, unsupported, and unknown boundaries; never
   silently carry verification to a newer version.

Credit is tied to accepted evidence, not only merged code. Co-authorship or a
pull-request mention can supplement the release-note credit but does not replace
the compatibility scope and evidence link.
