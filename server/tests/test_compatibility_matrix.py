from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from swiftagent.agents.claude import ClaudeCodeAdapter
from swiftagent.agents.claude import settings as claude_settings
from swiftagent.agents.codex import CodexAdapter
from swiftagent.agents.codex import settings as codex_settings
from swiftagent.agents.opencode import OpenCodeAdapter
from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_FIXTURE = FIXTURES / "claude_stream" / "fake_claude.py"
CODEX_FIXTURE = FIXTURES / "codex" / "fake_app_server.py"
OPENCODE_FIXTURE = FIXTURES / "opencode" / "fake_opencode.py"
MATRIX_FIXTURE = FIXTURES / "compatibility-v0.4.json"
COMMON_PROMPT = "Inspect the disposable fixture and report completion without network access."


class RecordingManager:
    def __init__(self):
        self.agent_events = []
        self.events = []

    async def broadcast_agent_event(self, event):
        self.agent_events.append(event)

    async def broadcast(self, event):
        self.events.append(event)

    async def request_permission(self, _request_id, event):
        self.events.append(event)
        return True

    async def request_question(self, _request_id, event):
        self.events.append(event)
        return ""


def make_task(agent_id: str, workspace: Path) -> Task:
    definition = agent_registry.definition(agent_id)
    task = Task(
        config=TaskConfig(
            prompt=COMMON_PROMPT,
            agent_id=agent_id,
            working_directory=str(workspace),
        ),
        status=TaskStatus.RUNNING,
        agent_id=definition.agent_id,
        adapter_id=definition.adapter_id,
        adapter_version=definition.adapter_version,
        capability_snapshot=definition.capabilities.model_dump(),
    )
    task_repo.save_task(task)
    task_repo.add_task_message(task.id, TaskMessage(role="user", content=COMMON_PROMPT))
    return task


@pytest.mark.asyncio
async def test_three_named_agents_complete_the_same_harmless_fixture_and_persist_history(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    claude_log = tmp_path / "claude.jsonl"
    codex_log = tmp_path / "codex.jsonl"
    opencode_log = tmp_path / "opencode.jsonl"
    monkeypatch.setenv("SWIFTAGENT_TEST_CLAUDE_LOG", str(claude_log))
    monkeypatch.setenv("SWIFTAGENT_TEST_OPENCODE_LOG", str(opencode_log))
    monkeypatch.delenv("SWIFTAGENT_TEST_CLAUDE_SCENARIO", raising=False)
    monkeypatch.delenv("SWIFTAGENT_TEST_OPENCODE_SCENARIO", raising=False)
    monkeypatch.delenv("SWIFTAGENT_TEST_OPENCODE_NO_ACP", raising=False)

    claude_settings.set_cli_path(str(CLAUDE_FIXTURE))
    claude_settings.set_model(None)
    claude_settings.set_permission_mode("default")
    opencode_settings.set_cli_path(str(OPENCODE_FIXTURE))
    opencode_settings.set_model(None)
    codex_settings.set_model(None)
    codex_settings.set_approval_policy("on-request")
    codex_settings.set_sandbox_mode("workspace-write")

    runs: list[tuple[Task, RecordingManager]] = []

    claude_task = make_task("claude-code", workspace)
    claude_manager = RecordingManager()
    claude = ClaudeCodeAdapter(claude_task, claude_manager)
    await claude.start()
    await asyncio.wait_for(claude.wait(), timeout=10)
    runs.append((claude_task, claude_manager))

    codex_task = make_task("codex", workspace)
    codex_manager = RecordingManager()
    codex = CodexAdapter(
        codex_task,
        codex_manager,
        command=[sys.executable, str(CODEX_FIXTURE), "--log", str(codex_log)],
    )
    await codex.start()
    await asyncio.wait_for(codex.wait(), timeout=10)
    runs.append((codex_task, codex_manager))

    opencode_task = make_task("opencode", workspace)
    opencode_manager = RecordingManager()
    opencode = OpenCodeAdapter(opencode_task, opencode_manager)
    await opencode.start()
    await asyncio.wait_for(opencode.wait(), timeout=10)
    runs.append((opencode_task, opencode_manager))

    for task, manager in runs:
        persisted = task_repo.get_task(task.id)
        assert persisted is not None and persisted.status is TaskStatus.COMPLETED
        assert persisted.summary
        assert any(message.role == "assistant" for message in persisted.messages)
        assert manager.agent_events[-1].type is AgentEventType.RUN_COMPLETED
        assert all(event.agent_id == task.agent_id for event in manager.agent_events)

    claude_args = json.loads(claude_log.read_text().splitlines()[0])["args"]
    assert claude_args[-1] == COMMON_PROMPT
    codex_messages = [json.loads(line) for line in codex_log.read_text().splitlines()]
    turn_start = next(message for message in codex_messages if message.get("method") == "turn/start")
    assert COMMON_PROMPT in json.dumps(turn_start)
    opencode_messages = [json.loads(line) for line in opencode_log.read_text().splitlines()]
    prompt = next(message for message in opencode_messages if message.get("method") == "prompt")
    assert prompt["prompt"] == COMMON_PROMPT


@pytest.mark.asyncio
async def test_claude_cancel_cannot_race_into_a_false_running_or_failed_state(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    claude_settings.set_cli_path(str(CLAUDE_FIXTURE))
    monkeypatch.setenv("SWIFTAGENT_TEST_CLAUDE_SCENARIO", "cancel")
    task = make_task("claude-code", workspace)
    adapter = ClaudeCodeAdapter(task, RecordingManager())

    await adapter.start()
    await asyncio.sleep(0.1)
    await asyncio.wait_for(adapter.cancel(), timeout=5)
    await asyncio.wait_for(adapter.wait(), timeout=5)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.CANCELLED
    assert adapter.running is False


@pytest.mark.asyncio
async def test_malformed_native_stream_cannot_poison_another_active_task(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    bad_task = make_task("codex", workspace)
    good_task = make_task("codex", workspace)
    bad = CodexAdapter(
        bad_task,
        RecordingManager(),
        command=[sys.executable, str(CODEX_FIXTURE), "--scenario", "malformed"],
    )
    good = CodexAdapter(
        good_task,
        RecordingManager(),
        command=[sys.executable, str(CODEX_FIXTURE), "--scenario", "basic"],
    )

    await asyncio.gather(bad.start(), good.start())
    await asyncio.wait_for(asyncio.gather(bad.wait(), good.wait()), timeout=10)

    malformed = task_repo.get_task(bad_task.id)
    unaffected = task_repo.get_task(good_task.id)
    assert malformed is not None and malformed.status is TaskStatus.FAILED
    assert unaffected is not None and unaffected.status is TaskStatus.COMPLETED
    assert "Codex fixture completed" in (unaffected.summary or "")


def test_machine_readable_matrix_covers_every_registry_entry_without_verified_lies():
    matrix = json.loads(MATRIX_FIXTURE.read_text())
    allowed = set(matrix["allowed_statuses"])
    rows = {row["agent_id"]: row for row in matrix["agents"]}
    definitions = {definition.agent_id: definition for definition in agent_registry.definitions()}
    assert set(rows) == set(definitions)

    fields = {
        "resume": "session_resume",
        "fork": "session_fork",
        "approvals": "approvals",
        "tools": "tool_events",
        "attachments": "attachments",
        "plans": "plan_updates",
        "usage": "usage",
        "cancel": "cancellation",
    }
    for agent_id, definition in definitions.items():
        row = rows[agent_id]
        for matrix_field, capability_field in fields.items():
            status = row[matrix_field]
            assert status in allowed
            declared = getattr(definition.capabilities, capability_field)
            if status == "verified":
                assert declared is True, f"{agent_id} verifies undeclared {matrix_field}"
            if status == "unsupported":
                assert declared is False, f"{agent_id} hides declared {matrix_field}"
        for status_field in ("authentication", "new_run", "native_safety", "strict_external_isolation"):
            assert row[status_field] in allowed
