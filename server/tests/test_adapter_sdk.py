from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from swiftagent.adapter_sdk import ADAPTER_API_VERSION, CONTRACT_SUITE_ID
from swiftagent.adapter_sdk.contract import run_contract
from swiftagent.adapter_sdk.loader import load_external_adapters
from swiftagent.adapter_sdk.manifest import AdapterManifest, load_manifest
from swiftagent.agents.registry import AgentRegistry
from swiftagent.models.agent import AgentCapabilities, AgentDefinition
from swiftagent.models.task import Task, TaskConfig

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "adapter-kit" / "example-adapter"
MANIFEST = EXAMPLE / "example-acp.adapter.json"
SCHEMA = ROOT / "adapter-kit" / "schema" / "adapter-manifest-v1.schema.json"


def test_manifest_and_public_schema_freeze_adapter_api_v1() -> None:
    manifest = load_manifest(MANIFEST)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert manifest.adapter_api_version == ADAPTER_API_VERSION == "1.0"
    assert manifest.compatibility is not None
    assert manifest.compatibility.contract_suite == CONTRACT_SUITE_ID
    assert schema["properties"]["adapter_api_version"]["const"] == ADAPTER_API_VERSION
    assert schema["additionalProperties"] is False
    assert schema["properties"]["protocol"]["const"] == "acp-v1"


def test_manifest_rejects_shells_unknown_fields_and_self_verified_isolation() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["command"] = ["bash", "-lc", "agent acp"]
    with pytest.raises(ValidationError, match="Shell executables are not allowed"):
        AdapterManifest.model_validate(payload)

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["capabilites"] = payload["capabilities"]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AdapterManifest.model_validate(payload)

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["capabilities"]["external_sandbox"] = "verified"
    with pytest.raises(ValidationError, match="cannot self-assign"):
        AdapterManifest.model_validate(payload)


@pytest.mark.asyncio
async def test_public_example_passes_new_resume_capabilities_cancellation_and_failure_contract() -> None:
    report = await run_contract(MANIFEST)

    assert report["result"] == "passed"
    assert report["contract_suite"] == CONTRACT_SUITE_ID
    assert report["resume_checked"] is True
    assert report["cancellation_checked"] is True
    assert report["failure_checked"] is True
    assert report["failure_recovery_checked"] is True
    assert "run.failed" in report["failure_event_types"]
    assert report["security"] == {
        "shell_used": False,
        "temporary_workspace": True,
        "network_required": False,
        "environment_allowlist": [],
    }
    assert set(report["required_event_types"]).issubset(report["event_types"])


def test_contract_fixture_accepts_bounded_failure_arguments_matching_schema() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    contract_schema = schema["$defs"]["contract"]["properties"]

    assert "failure_arguments" in contract_schema
    assert contract_schema["failure_arguments"]["maxItems"] == 16
    assert payload["contract"]["failure_arguments"] == ["--scenario", "fail"]

    manifest = AdapterManifest.model_validate(payload)
    assert manifest.contract is not None
    assert manifest.contract.failure_arguments == ["--scenario", "fail"]

    payload["contract"]["failure_arguments"] = [""]
    with pytest.raises(ValidationError, match="Failure arguments must be non-empty"):
        AdapterManifest.model_validate(payload)


def test_local_manifest_registers_without_core_edits_and_forwards_only_allowlisted_env(
    tmp_path: Path, monkeypatch
) -> None:
    adapter_dir = tmp_path / "adapters"
    adapter_dir.mkdir()
    shutil.copy2(EXAMPLE / "fake_agent.py", adapter_dir / "fake_agent.py")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["environment_allowlist"] = ["EXAMPLE_ALLOWED"]
    (adapter_dir / "example.adapter.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SWIFTAGENT_ADAPTER_DIR", str(adapter_dir))
    monkeypatch.setenv("EXAMPLE_ALLOWED", "visible-to-adapter")
    monkeypatch.setenv("SECRET_NOT_ALLOWED", "must-not-cross-boundary")

    registry = AgentRegistry()
    errors = load_external_adapters(registry, tmp_path / "data")
    definition = registry.definition("example-acp-agent")
    statuses = registry.statuses(refresh=True)
    task = Task(
        config=TaskConfig(prompt="contract", agent_id=definition.agent_id),
        agent_id=definition.agent_id,
        adapter_id=definition.adapter_id,
        adapter_version=definition.adapter_version,
        capability_snapshot=definition.capabilities.model_dump(),
    )
    adapter = registry.create(definition.agent_id, task, object())

    assert errors == []
    assert definition.adapter_id == "example-acp-v1"
    assert definition.trust_level == "local_custom"
    assert definition.trust_evidence is None
    assert statuses[0].installed is True
    assert statuses[0].version == "1.0.0"
    assert adapter._environment["EXAMPLE_ALLOWED"] == "visible-to-adapter"  # noqa: SLF001
    assert "SECRET_NOT_ALLOWED" not in adapter._environment  # noqa: SLF001


def test_manifest_cannot_replace_a_registered_agent_id(tmp_path: Path, monkeypatch) -> None:
    adapter_dir = tmp_path / "adapters"
    adapter_dir.mkdir()
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["agent_id"] = "codex"
    (adapter_dir / "collision.adapter.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SWIFTAGENT_ADAPTER_DIR", str(adapter_dir))

    registry = AgentRegistry()
    registry.register(
        AgentDefinition(
            agent_id="codex",
            display_name="Built-in Codex",
            adapter_id="codex-built-in",
            adapter_version="1.0.0",
            protocol="fixture",
            capabilities=AgentCapabilities(),
        ),
        lambda task, _manager: task,
    )

    errors = load_external_adapters(registry, tmp_path / "data")

    assert len(errors) == 1
    assert "already registered: codex" in errors[0]
    assert registry.definition("codex").adapter_id == "codex-built-in"


def test_invalid_manifest_error_is_bounded_and_does_not_block_valid_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    adapter_dir = tmp_path / "adapters"
    adapter_dir.mkdir()
    shutil.copy2(EXAMPLE / "fake_agent.py", adapter_dir / "fake_agent.py")
    shutil.copy2(MANIFEST, adapter_dir / "valid.adapter.json")
    (adapter_dir / "broken.adapter.json").write_text(
        json.dumps({"schema_version": 1, "unexpected": "x" * 10_000}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SWIFTAGENT_ADAPTER_DIR", str(adapter_dir))

    registry = AgentRegistry()
    errors = load_external_adapters(registry, tmp_path / "data")

    assert registry.definition("example-acp-agent").adapter_id == "example-acp-v1"
    assert len(errors) == 1
    assert errors[0].startswith("broken.adapter.json:")
    assert len(errors[0]) <= 512
