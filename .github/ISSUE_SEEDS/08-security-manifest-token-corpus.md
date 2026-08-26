## Outcome

Expand the local manifest security corpus so token substitution cannot become
shell interpolation, path confusion, or accidental environment forwarding.

## Acceptance criteria

- Parameterized tests cover `${manifest_dir}` and `${python}` in multiple argv
  positions plus literal `$()`, backticks, glob characters, spaces, and Unicode.
- No case invokes a shell, expands a glob, evaluates nested text, or forwards an
  environment name outside the baseline plus explicit allowlist.
- Relative/missing executables, symlinked manifest directories, oversized args,
  duplicate env names, and invalid state paths fail with bounded diagnostics.
- Valid literal values reach the fake process byte-for-byte on macOS and Linux
  CI without a provider/model call.
- The security checklist and threat boundary describe any newly discovered
  limitation.
- `make lint`, `make test`, and `make adapter-kit-test` pass.
