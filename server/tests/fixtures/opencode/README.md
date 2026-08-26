# OpenCode fixtures

`fake_opencode.py` is a deterministic, no-network stand-in for OpenCode 1.18.13.
It exposes the version, model catalog, ACP v1 handshake/session/configuration,
and reduced JSON-run stream used by the built-in adapter contract tests.

The verified live probe for this section only initialized local OpenCode ACP and
created an empty, unshared session. It did not send a model prompt.
