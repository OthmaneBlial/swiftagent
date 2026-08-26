from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from swiftagent.agents.codex.adapter import CodexAdapter
from swiftagent.agents.codex.status import get_status
from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo

FIXTURES = Path(__file__).parent / "fixtures" / "codex"
FAKE_SERVER = FIXTURES / "fake_app_server.py"


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
        return "fixture answer"


def make_task(workspace: Path, *, session_id: str | None = None) -> Task:
    definition = agent_registry.definition("codex")
    return Task(
        config=TaskConfig(
            prompt="Exercise the Codex app-server contract.",
            agent_id="codex",
            working_directory=str(workspace),
            model_id="fixture-model",
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


def fixture_command(scenario: str, log_path: Path) -> list[str]:
    return [
        sys.executable,
        str(FAKE_SERVER),
        "--scenario",
        scenario,
        "--log",
        str(log_path),
    ]


def read_log(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def codex_workspace(client, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    settings_repo.set_value("codex_approval_policy", "on-request")
    settings_repo.set_value("codex_sandbox_mode", "workspace-write")
    settings_repo.set_value("codex_allow_dangerous_bypass", "0")
    return workspace


@pytest.mark.asyncio
async def test_codex_new_turn_maps_stream_approval_usage_and_persistence(
    codex_workspace, tmp_path
):
    log_path = tmp_path / "codex-basic.jsonl"
    task = make_task(codex_workspace)
    persist_task(task)
    manager = RecordingManager(approve=True)
    adapter = CodexAdapter(task, manager, command=fixture_command("basic", log_path))

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.native_session_id == "codex-fixture-thread"
    assert persisted.summary == "Codex fixture completed."
    assert persisted.capability_snapshot["available_models"][0]["id"] == "fixture-model"
    assert persisted.capability_snapshot["native_sandbox_mode"] == "workspace-write"
    event_types = [event.type for event in manager.agent_events]
    assert AgentEventType.RUN_STARTED in event_types
    assert AgentEventType.APPROVAL_REQUESTED in event_types
    assert AgentEventType.APPROVAL_RESOLVED in event_types
    assert AgentEventType.TOOL_STARTED in event_types
    assert AgentEventType.TOOL_COMPLETED in event_types
    assert AgentEventType.PLAN_UPDATED in event_types
    assert AgentEventType.USAGE_UPDATED in event_types
    assert event_types[-1] is AgentEventType.RUN_COMPLETED

    messages = read_log(log_path)
    assert [message["method"] for message in messages if "method" in message][:4] == [
        "initialize",
        "initialized",
        "account/read",
        "model/list",
    ]
    turn_start = next(message for message in messages if message.get("method") == "turn/start")
    assert turn_start["params"]["approvalPolicy"] == "on-request"
    assert turn_start["params"]["sandboxPolicy"]["type"] == "workspaceWrite"
    assert turn_start["params"]["model"] == "fixture-model"
    approval = next(message for message in messages if message.get("id") == "fixture-approval")
    assert approval["result"] == {"decision": "accept"}


@pytest.mark.asyncio
async def test_codex_resume_and_rejected_approval_fail_with_native_error(
    codex_workspace, tmp_path
):
    log_path = tmp_path / "codex-resume.jsonl"
    task = make_task(codex_workspace, session_id="codex-fixture-thread")
    persist_task(task)
    manager = RecordingManager(approve=False)
    adapter = CodexAdapter(task, manager, command=fixture_command("reject", log_path))

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None
    assert persisted.status is TaskStatus.FAILED
    assert persisted.result is not None
    assert persisted.result.error == "Fixture approval was declined"
    messages = read_log(log_path)
    assert any(message.get("method") == "thread/resume" for message in messages)
    approval = next(message for message in messages if message.get("id") == "fixture-approval")
    assert approval["result"] == {"decision": "decline"}


@pytest.mark.asyncio
async def test_codex_tool_failure_is_preserved_without_poisoning_completed_turn(
    codex_workspace, tmp_path
):
    task = make_task(codex_workspace)
    persist_task(task)
    manager = RecordingManager()
    adapter = CodexAdapter(
        task,
        manager,
        command=fixture_command("tool-failure", tmp_path / "tool-failure.jsonl"),
    )

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.COMPLETED
    tool_event = next(
        event for event in manager.agent_events if event.type is AgentEventType.TOOL_COMPLETED
    )
    assert tool_event.payload["status"] == "failed"
    assert "tool failure" in (persisted.summary or "")


@pytest.mark.asyncio
async def test_codex_interrupt_maps_to_cancelled_and_process_cleanup(codex_workspace, tmp_path):
    task = make_task(codex_workspace)
    persist_task(task)
    manager = RecordingManager()
    adapter = CodexAdapter(
        task,
        manager,
        command=fixture_command("cancel", tmp_path / "cancel.jsonl"),
    )

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.cancel(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.CANCELLED
    assert adapter.running is False


@pytest.mark.asyncio
async def test_malformed_codex_stream_fails_only_its_task(codex_workspace, tmp_path):
    task = make_task(codex_workspace)
    persist_task(task)
    adapter = CodexAdapter(
        task,
        RecordingManager(),
        command=fixture_command("malformed", tmp_path / "malformed.jsonl"),
    )

    await asyncio.wait_for(adapter.start(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.FAILED
    assert "malformed JSON" in (persisted.result.error if persisted.result else "")


def test_codex_status_uses_free_version_and_login_probes(client, monkeypatch):
    import swiftagent.agents.codex.status as status_module

    calls: list[tuple[str, ...]] = []

    def fake_run(executable, *args, timeout=5):
        calls.append((executable, *args))
        if args == ("--version",):
            return subprocess.CompletedProcess([], 0, "codex-cli 0.149.1\n", "")
        return subprocess.CompletedProcess([], 0, "Logged in using ChatGPT\n", "")

    monkeypatch.setattr(status_module, "resolve_cli_path", lambda: "/opt/tools/codex")
    monkeypatch.setattr(status_module, "_run", fake_run)
    status = get_status(agent_registry.definition("codex"))

    assert status.installed is True
    assert status.compatible is True
    assert status.auth_status == "ready"
    assert calls == [
        ("/opt/tools/codex", "--version"),
        ("/opt/tools/codex", "app-server", "--help"),
        ("/opt/tools/codex", "login", "status"),
    ]


def test_codex_status_rejects_versions_before_the_generated_contract(client, monkeypatch):
    import swiftagent.agents.codex.status as status_module

    def fake_run(executable, *args, timeout=5):
        if args == ("--version",):
            return subprocess.CompletedProcess([], 0, "codex-cli 0.148.0\n", "")
        return subprocess.CompletedProcess([], 1, "", "Not logged in")

    monkeypatch.setattr(status_module, "resolve_cli_path", lambda: "/opt/tools/codex")
    monkeypatch.setattr(status_module, "_run", fake_run)
    status = get_status(agent_registry.definition("codex"))

    assert status.installed is True
    assert status.compatible is False
    assert status.auth_status == "action_required"
    assert "predates" in (status.detail or "")


def test_codex_dangerous_native_bypass_requires_explicit_confirmation(client):
    rejected = client.put(
        "/api/settings",
        json={
            "codex_approval_policy": "never",
            "codex_sandbox_mode": "danger-full-access",
            "codex_allow_dangerous_bypass": False,
        },
    )
    assert rejected.status_code == 400
    assert "disables both native safety layers" in rejected.json()["detail"]

    accepted = client.put(
        "/api/settings",
        json={
            "codex_approval_policy": "never",
            "codex_sandbox_mode": "danger-full-access",
            "codex_allow_dangerous_bypass": True,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["codex_allow_dangerous_bypass"] is True


def test_codex_fixture_manifest_tracks_generated_protocol_version():
    manifest = json.loads((FIXTURES / "schema-0.149.1-manifest.json").read_text())
    assert manifest["codexVersion"] == "codex-cli 0.149.1"
    assert manifest["protocol"] == "codex-app-server-v2"
    assert "turn/interrupt" in manifest["methods"]
