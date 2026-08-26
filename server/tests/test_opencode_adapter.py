from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from swiftagent.agents.opencode import OpenCodeAdapter
from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.agents.opencode.status import get_status
from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo

FIXTURES = Path(__file__).parent / "fixtures" / "opencode"
FAKE_OPENCODE = FIXTURES / "fake_opencode.py"


class RecordingManager:
    def __init__(self, *, approve: bool = True):
        self.approve = approve
        self.agent_events = []
        self.events = []

    async def broadcast_agent_event(self, event):
        self.agent_events.append(event)

    async def broadcast(self, event):
        self.events.append(event)

    async def request_permission(self, _request_id, event):
        self.events.append(event)
        return self.approve

    async def request_question(self, _request_id, event):
        self.events.append(event)
        return ""


def make_task(workspace: Path, *, model: str | None = None, session_id: str | None = None) -> Task:
    definition = agent_registry.definition("opencode")
    return Task(
        config=TaskConfig(
            prompt="Exercise OpenCode without sharing the session.",
            agent_id=definition.agent_id,
            working_directory=str(workspace),
            model_id=model,
        ),
        status=TaskStatus.RUNNING,
        agent_id=definition.agent_id,
        adapter_id=definition.adapter_id,
        adapter_version=definition.adapter_version,
        native_session_id=session_id,
        session_id=session_id,
        capability_snapshot=definition.capabilities.model_dump(),
    )


def persist_task(task: Task) -> None:
    task_repo.save_task(task)
    task_repo.add_task_message(task.id, TaskMessage(role="user", content=task.config.prompt))


def configure_fixture(workspace: Path, log: Path) -> None:
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    opencode_settings.set_cli_path(str(FAKE_OPENCODE))
    opencode_settings.set_model(None)
    log.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_opencode_prefers_acp_discovers_model_and_never_shares(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_LOG", str(log))
    monkeypatch.delenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", raising=False)

    task = make_task(workspace, model="fixture/second-model")
    persist_task(task)
    manager = RecordingManager()
    adapter = OpenCodeAdapter(task, manager)

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.native_session_id == "fake-opencode-session"
    assert persisted.capability_snapshot["transport"] == "acp-v1"
    assert persisted.capability_snapshot["available_models"] == [
        "fixture/free-model",
        "fixture/second-model",
    ]
    assert persisted.capability_snapshot["effective_model"] == "fixture/second-model"
    assert persisted.capability_snapshot["session_sharing"] is False
    assert (workspace / "opencode-output.txt").read_text() == "model=fixture/second-model\n"
    assert "OpenCode ACP fixture completed" in (persisted.summary or "")

    event_types = [event.type for event in manager.agent_events]
    assert AgentEventType.APPROVAL_REQUESTED in event_types
    assert AgentEventType.TOOL_COMPLETED in event_types
    assert AgentEventType.PLAN_UPDATED in event_types
    assert AgentEventType.USAGE_UPDATED in event_types
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert {record.get("model") for record in records} >= {"fixture/second-model"}
    launched = next(record["args"] for record in records if record["method"] == "argv" and record["args"][0] == "acp")
    assert "--share" not in launched
    assert "--auto" not in launched


@pytest.mark.asyncio
async def test_opencode_acp_resumes_only_the_explicit_native_session(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_LOG", str(log))
    monkeypatch.delenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", raising=False)
    task = make_task(workspace, session_id="fake-opencode-session")
    persist_task(task)

    adapter = OpenCodeAdapter(task, RecordingManager())
    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.COMPLETED
    assert persisted.native_session_id == "fake-opencode-session"


@pytest.mark.asyncio
async def test_opencode_json_fallback_is_reduced_and_structured(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_LOG", str(log))
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", "1")
    task = make_task(workspace, model="fixture/free-model")
    persist_task(task)
    manager = RecordingManager()

    adapter = OpenCodeAdapter(task, manager)
    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.capability_snapshot["transport"] == "opencode-json-run"
    assert persisted.capability_snapshot["approvals"] is False
    assert persisted.capability_snapshot["plan_updates"] is False
    assert persisted.capability_snapshot["native_sandbox"] is False
    assert "OpenCode JSON fixture/free-model." in (persisted.summary or "")
    event_types = [event.type for event in manager.agent_events]
    assert AgentEventType.TOOL_STARTED in event_types
    assert AgentEventType.TOOL_COMPLETED in event_types
    assert AgentEventType.USAGE_UPDATED in event_types
    assert AgentEventType.APPROVAL_REQUESTED not in event_types

    records = [json.loads(line) for line in log.read_text().splitlines()]
    launched = next(
        record["args"]
        for record in records
        if record["method"] == "argv" and record["args"][:2] == ["run", "--format"]
    )
    assert launched[:5] == ["run", "--format", "json", "--dir", str(workspace)]
    assert "--share" not in launched
    assert "--auto" not in launched
    assert "--continue" not in launched


@pytest.mark.asyncio
async def test_opencode_malformed_fallback_fails_only_its_task(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", "1")
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_SCENARIO", "malformed")
    task = make_task(workspace)
    persist_task(task)

    adapter = OpenCodeAdapter(task, RecordingManager())
    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.FAILED
    assert persisted.result is not None
    assert "malformed JSON" in (persisted.result.error or "")


@pytest.mark.asyncio
async def test_opencode_json_fallback_cancels_process_group(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", "1")
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_SCENARIO", "cancel")
    task = make_task(workspace)
    persist_task(task)

    adapter = OpenCodeAdapter(task, RecordingManager())
    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.sleep(0.1)
    await asyncio.wait_for(adapter.cancel(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.CANCELLED
    assert adapter.running is False


def test_opencode_status_is_version_gated_and_uses_cli_model_catalog(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "opencode-log.jsonl"
    configure_fixture(workspace, log)
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_LOG", str(log))
    monkeypatch.delenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", raising=False)

    status = get_status(agent_registry.definition("opencode"))
    assert status.installed is True
    assert status.compatible is True
    assert status.protocol == "acp-v1"
    assert status.auth_status == "ready"
    assert [model.id for model in status.models] == [
        "fixture/free-model",
        "fixture/second-model",
    ]
    assert status.capabilities.approvals is True
    records = [json.loads(line) for line in log.read_text().splitlines()]
    model_probe = next(
        record for record in records if record["method"] == "argv" and record["args"] == ["models"]
    )
    assert model_probe["cwd"] == str(workspace)

    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", "1")
    fallback = get_status(agent_registry.definition("opencode"))
    assert fallback.protocol == "opencode-json-run"
    assert fallback.capabilities.approvals is False
    assert fallback.capabilities.plan_updates is False
    assert "reduced JSON-run mode" in (fallback.detail or "")


def test_opencode_contract_manifest_records_no_live_model_prompt():
    manifest = json.loads((FIXTURES / "contract-1.18.13.json").read_text())
    assert manifest["version"] == "1.18.13"
    assert manifest["preferred_transport"].startswith("opencode acp")
    assert manifest["live_probe"]["protocol_version"] == 1
    assert manifest["live_probe"]["session_sharing_enabled"] is False
    assert manifest["live_probe"]["model_prompt_sent"] is False
