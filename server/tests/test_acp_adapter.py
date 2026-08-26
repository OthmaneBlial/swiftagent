from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from acp import RequestError

from swiftagent.agents.acp.adapter import AcpAdapter
from swiftagent.agents.acp.client import AcpClientBridge
from swiftagent.agents.acp.settings import get_command
from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo

FIXTURES = Path(__file__).parent / "fixtures" / "acp"
FAKE_AGENT = FIXTURES / "fake_agent.py"


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


def make_task(workspace: Path, *, session_id: str | None = None) -> Task:
    definition = agent_registry.definition("acp-agent")
    return Task(
        config=TaskConfig(
            prompt="Exercise every stable ACP callback.",
            agent_id=definition.agent_id,
            working_directory=str(workspace),
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


@pytest.mark.asyncio
async def test_acp_adapter_exercises_official_callbacks_and_persists_negotiation(
    client, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture-input.txt").write_text("selected workspace", encoding="utf-8")
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    task = make_task(workspace)
    persist_task(task)
    manager = RecordingManager()
    adapter = AcpAdapter(task, manager, command=[sys.executable, str(FAKE_AGENT)])

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.native_session_id == "fake-acp-session"
    assert persisted.capability_snapshot["session_resume"] is True
    assert persisted.result is not None and persisted.result.success is True
    assert "ACP fixture completed" in (persisted.summary or "")
    assert "private fixture thought" not in (persisted.summary or "")
    assert (workspace / "fixture-output.txt").read_text(encoding="utf-8") == (
        "ACP copied: selected workspace\n"
    )
    event_types = [event.type for event in manager.agent_events]
    assert AgentEventType.RUN_STARTED in event_types
    assert AgentEventType.APPROVAL_REQUESTED in event_types
    assert AgentEventType.APPROVAL_RESOLVED in event_types
    assert AgentEventType.TOOL_STARTED in event_types
    assert AgentEventType.TOOL_COMPLETED in event_types
    assert AgentEventType.PLAN_UPDATED in event_types
    assert AgentEventType.USAGE_UPDATED in event_types
    assert event_types[-1] is AgentEventType.RUN_COMPLETED
    assert any(
        "truncated=True" in event.payload.get("content", "")
        for event in manager.agent_events
        if event.type is AgentEventType.MESSAGE_COMPLETED
    )


@pytest.mark.asyncio
async def test_acp_adapter_loads_native_session_and_cancels_cleanly(client, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    task = make_task(workspace, session_id="fake-acp-session")
    task.capability_snapshot["session_resume"] = True
    persist_task(task)
    manager = RecordingManager()
    adapter = AcpAdapter(
        task,
        manager,
        command=[sys.executable, str(FAKE_AGENT), "--scenario", "cancel"],
    )

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.cancel(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.CANCELLED
    assert adapter.running is False


@pytest.mark.asyncio
async def test_acp_file_callbacks_reject_relative_and_outside_selected_workspace(
    client, tmp_path
):
    workspace = tmp_path / "selected"
    workspace.mkdir()
    task = make_task(workspace, session_id="fake-acp-session")
    bridge = AcpClientBridge(AcpAdapter(task, RecordingManager(), command=["unused"]), workspace)

    with pytest.raises(RequestError):
        await bridge.read_text_file("fake-acp-session", "relative.txt")
    with pytest.raises(RequestError):
        await bridge.write_text_file(
            "fake-acp-session", str(tmp_path / "outside.txt"), "must not escape"
        )

    inside = workspace / "nested" / "inside.txt"
    await bridge.write_text_file("fake-acp-session", str(inside), "contained")
    response = await bridge.read_text_file("fake-acp-session", str(inside))
    assert response.content == "contained"
    assert not (tmp_path / "outside.txt").exists()


def test_acp_setting_requires_a_literal_argument_array(client):
    client.put("/api/settings", json={"acp_command_json": '["existing-agent"]'})
    invalid = client.put("/api/settings", json={"acp_command_json": "agent --acp"})
    assert invalid.status_code == 400
    assert get_command() == ["existing-agent"]

    updated = client.put(
        "/api/settings",
        json={"acp_command_json": '["agent binary", "--acp", "literal value"]'},
    )
    assert updated.status_code == 200
    assert get_command() == ["agent binary", "--acp", "literal value"]
    assert json.loads(updated.json()["acp_command_json"]) == [
        "agent binary",
        "--acp",
        "literal value",
    ]


def test_acp_fixture_records_stable_schema_source_and_protocol_version():
    transcript = json.loads((FIXTURES / "schema-v1.21.0-transcript.json").read_text())
    assert transcript["protocolVersion"] == 1
    assert transcript["source"].endswith("/schema-v1.21.0")
    assert {message["method"] for message in transcript["messages"]} >= {
        "initialize",
        "session/update",
        "session/request_permission",
        "session/cancel",
    }
