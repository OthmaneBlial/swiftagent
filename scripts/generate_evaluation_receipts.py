"""Run release-scoped adapter fixtures and write bounded evaluation receipts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EVALUATIONS = (
    {
        "agent_id": "claude-code",
        "tested_contract": "Claude Code stream-json fixture 2.1.52; live CLI version unknown",
        "test": "tests/test_claude_contract.py::test_successful_stream_contract_preserves_session_tools_and_result",
        "boundary": "Fixture-backed only; no live version or provider/model call.",
    },
    {
        "agent_id": "acp-agent",
        "tested_contract": "ACP v1, schema v1.21.0, official Python SDK 0.12.x fixture",
        "test": "tests/test_acp_adapter.py::test_acp_adapter_exercises_official_callbacks_and_persists_negotiation",
        "boundary": "Deterministic local ACP process; agent-specific auth and resume are negotiated.",
    },
    {
        "agent_id": "codex",
        "tested_contract": "Codex CLI 0.149.1 app-server v2 fixture",
        "test": "tests/test_codex_adapter.py::test_codex_new_turn_maps_stream_approval_usage_and_persistence",
        "boundary": "Deterministic app-server fixture; no provider/model call.",
    },
    {
        "agent_id": "opencode",
        "tested_contract": "OpenCode CLI 1.18.13 ACP v1 fixture",
        "test": "tests/test_opencode_adapter.py::test_opencode_prefers_acp_discovers_model_and_never_shares",
        "boundary": "Deterministic ACP fixture; provider execution is not evaluated.",
    },
    {
        "agent_id": "generic-command",
        "tested_contract": "literal-subprocess manifest v1 and fixture 1.0.0",
        "test": "tests/test_generic_command_adapter.py::test_disposable_test_is_required_and_uses_temporary_workspace",
        "boundary": "Text-only disposable fixture; no auth, tools, approvals, plans, or usage.",
    },
)


def main() -> int:
    project = tomllib.loads((ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8"))
    release = f"v{project['project']['version']}"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    DIST.mkdir(exist_ok=True)

    for evaluation in EVALUATIONS:
        command = [sys.executable, "-m", "pytest", evaluation["test"], "-q"]
        started = time.monotonic()
        result = subprocess.run(
            command,
            cwd=ROOT / "server",
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration_ms = round((time.monotonic() - started) * 1_000)
        output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            raise RuntimeError(f"{evaluation['agent_id']} evaluation failed:\n{output[-4_000:]}")
        receipt = {
            "schema_version": 1,
            "kind": "swiftagent-adapter-evaluation",
            "release": release,
            "source_commit": commit,
            "agent_id": evaluation["agent_id"],
            "tested_contract": evaluation["tested_contract"],
            "command": f"cd server && {Path(sys.executable).name} -m pytest {evaluation['test']} -q",
            "result": "passed",
            "duration_ms": duration_ms,
            "provider_or_model_call": False,
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "boundary": evaluation["boundary"],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        destination = DIST / f"swiftagent-{release}-{evaluation['agent_id']}-evaluation.json"
        destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(destination.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
