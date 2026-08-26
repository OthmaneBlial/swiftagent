from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from swiftagent.agents.generic_command import GenericCommandAdapter
from swiftagent.agents.generic_command import settings as generic_settings
from swiftagent.agents.generic_command.manifest import parse_manifest
from swiftagent.agents.generic_command.status import get_status
from swiftagent.agents.generic_command.tester import run_disposable_test
from swiftagent.agents.registry import agent_registry
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo

FIXTURES = Path(__file__).parent / "fixtures" / "generic_command"
FAKE_AGENT = FIXTURES / "fake_text_agent.py"


class RecordingManager:
    def __init__(self):
        self.agent_events = []
        self.events = []

    async def broadcast_agent_event(self, event):
        self.agent_events.append(event)

    async def broadcast(self, event):
        self.events.append(event)

    async def request_permission(self, _request_id, event):
        raise AssertionError(f"generic command requested a permission: {event}")

    async def request_question(self, _request_id, event):
        raise AssertionError(f"generic command requested a question: {event}")


def manifest_json(
    *,
    prompt_transport: str = "stdin",
    arguments: list[str] | None = None,
    timeout_seconds: int = 5,
    max_output_bytes: int = 65_536,
) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "name": "Fixture text adapter",
            "executable": str(FAKE_AGENT),
            "arguments": arguments or [],
            "prompt_transport": prompt_transport,
            "cwd_mode": "task",
            "timeout_seconds": timeout_seconds,
            "environment_allowlist": [
                "PATH",
                "LANG",
                "LC_ALL",
                "SWIFTAGENT_TEST_GENERIC_LOG",
                "SWIFTAGENT_TEST_GENERIC_SCENARIO",
            ],
            "max_output_bytes": max_output_bytes,
            "version_probe": {
                "arguments": ["--version"],
                "expected_output_prefix": "generic-fixture 1.0.0",
                "timeout_seconds": 3,
            },
        }
    )


def configure_manifest(workspace: Path, raw: str) -> None:
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    generic_settings.set_manifest_json(raw)


def make_task(workspace: Path, prompt: str) -> Task:
    definition = agent_registry.definition("generic-command")
    return Task(
        config=TaskConfig(
            prompt=prompt,
            agent_id=definition.agent_id,
            working_directory=str(workspace),
        ),
        status=TaskStatus.RUNNING,
        agent_id=definition.agent_id,
        adapter_id=definition.adapter_id,
        adapter_version=definition.adapter_version,
        capability_snapshot=definition.capabilities.model_dump(),
    )


def persist_task(task: Task) -> None:
    task_repo.save_task(task)
    task_repo.add_task_message(task.id, TaskMessage(role="user", content=task.config.prompt))


def test_generic_manifest_rejects_shell_like_or_unsafe_shapes():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_manifest("agent --flag")
    with pytest.raises(ValueError, match="environment"):
        parse_manifest(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "bad",
                    "executable": "agent",
                    "environment_allowlist": ["BAD-NAME"],
                }
            )
        )
    with pytest.raises(ValueError, match="literal"):
        parse_manifest(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "bad",
                    "executable": "bad\u0000path",
                }
            )
        )


@pytest.mark.asyncio
async def test_disposable_test_is_required_and_uses_temporary_workspace(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "generic-log.jsonl"
    monkeypatch.setenv("SWIFTAGENT_TEST_GENERIC_LOG", str(log))
    configure_manifest(workspace, manifest_json())

    before = get_status(agent_registry.definition("generic-command"))
    assert before.installed is True
    assert before.compatible is False
    assert "disabled" in (before.detail or "")

    result = await run_disposable_test()
    assert result.success is True
    assert result.stdout.strip() == "SWIFTAGENT_ADAPTER_OK"
    assert result.version_output == "generic-fixture 1.0.0"
    assert result.sandbox_notice is not None and "not OS-isolated" in result.sandbox_notice

    after = get_status(agent_registry.definition("generic-command"))
    assert after.compatible is True
    assert after.version == "generic-fixture 1.0.0"
    record = json.loads(log.read_text().splitlines()[0])
    assert record["cwd"].startswith("/private/") or record["cwd"].startswith("/tmp/")
    assert "swiftagent-adapter-test-" in record["cwd"]
    assert not Path(record["cwd"]).exists()


@pytest.mark.asyncio
async def test_generic_stdin_run_streams_text_with_only_declared_capabilities(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log = tmp_path / "generic-log.jsonl"
    monkeypatch.setenv("SWIFTAGENT_TEST_GENERIC_LOG", str(log))
    monkeypatch.setenv("SWIFTAGENT_TEST_SECRET", "must-not-reach-child")
    configure_manifest(workspace, manifest_json())
    await run_disposable_test()
    log.unlink()

    task = make_task(workspace, "hello from stdin")
    persist_task(task)
    manager = RecordingManager()
    adapter = GenericCommandAdapter(task, manager)
    await adapter.start()
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.COMPLETED
    assert persisted.summary == "generic:hello from stdin"
    assert persisted.capability_snapshot["transport"] == "literal-subprocess"
    assert persisted.capability_snapshot["tool_events"] is False
    assert persisted.capability_snapshot["approvals"] is False
    assert persisted.capability_snapshot["session_resume"] is False
    event_types = [event.type for event in manager.agent_events]
    assert AgentEventType.MESSAGE_DELTA in event_types
    assert AgentEventType.MESSAGE_COMPLETED in event_types
    assert AgentEventType.TOOL_STARTED not in event_types
    record = json.loads(log.read_text().splitlines()[0])
    assert "SWIFTAGENT_TEST_SECRET" not in record["environment"]


@pytest.mark.asyncio
async def test_argument_prompt_is_literal_and_never_interpreted_by_a_shell(
    client, tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    configure_manifest(
        workspace,
        manifest_json(prompt_transport="argument", arguments=["--argument"]),
    )
    await run_disposable_test()
    prompt = "$(touch should-not-exist); `touch also-not-exist`"
    task = make_task(workspace, prompt)
    persist_task(task)

    adapter = GenericCommandAdapter(task, RecordingManager())
    await adapter.start()
    await asyncio.wait_for(adapter.wait(), timeout=10)

    persisted = task_repo.get_task(task.id)
    assert persisted is not None and persisted.status is TaskStatus.COMPLETED
    assert prompt in (persisted.summary or "")
    assert not (workspace / "should-not-exist").exists()
    assert not (workspace / "also-not-exist").exists()


@pytest.mark.asyncio
async def test_generic_timeout_and_output_limit_fail_cleanly(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    configure_manifest(workspace, manifest_json(timeout_seconds=1, max_output_bytes=1_024))
    await run_disposable_test()

    monkeypatch.setenv("SWIFTAGENT_TEST_GENERIC_SCENARIO", "sleep")
    timeout_task = make_task(workspace, "time out")
    persist_task(timeout_task)
    timeout_adapter = GenericCommandAdapter(timeout_task, RecordingManager())
    await timeout_adapter.start()
    await asyncio.wait_for(timeout_adapter.wait(), timeout=5)
    timed_out = task_repo.get_task(timeout_task.id)
    assert timed_out is not None and timed_out.status is TaskStatus.FAILED
    assert "timed out" in ((timed_out.result and timed_out.result.error) or "")

    monkeypatch.setenv("SWIFTAGENT_TEST_GENERIC_SCENARIO", "spam")
    output_task = make_task(workspace, "too much")
    persist_task(output_task)
    output_adapter = GenericCommandAdapter(output_task, RecordingManager())
    await output_adapter.start()
    await asyncio.wait_for(output_adapter.wait(), timeout=5)
    oversized = task_repo.get_task(output_task.id)
    assert oversized is not None and oversized.status is TaskStatus.FAILED
    assert "stdout exceeded" in ((oversized.result and oversized.result.error) or "")


def test_changed_manifest_clears_receipt_and_api_test_reenables(client, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings_repo.set_workspace_dir(str(workspace))
    settings_repo.set_sandbox_mode("fallback")
    raw = manifest_json()
    saved = client.put("/api/settings", json={"generic_command_manifest_json": raw})
    assert saved.status_code == 200
    disabled = client.get("/api/agents?refresh=true").json()["agents"]
    generic = next(agent for agent in disabled if agent["agent_id"] == "generic-command")
    assert generic["compatible"] is False

    tested = client.post("/api/agents/generic-command/test")
    assert tested.status_code == 200
    enabled = client.get("/api/agents?refresh=true").json()["agents"]
    generic = next(agent for agent in enabled if agent["agent_id"] == "generic-command")
    assert generic["compatible"] is True

    same = client.put("/api/settings", json={"generic_command_manifest_json": raw})
    assert same.status_code == 200
    assert get_status(agent_registry.definition("generic-command")).compatible is True

    changed = json.loads(raw)
    changed["timeout_seconds"] = 6
    updated = client.put(
        "/api/settings",
        json={"generic_command_manifest_json": json.dumps(changed)},
    )
    assert updated.status_code == 200
    assert get_status(agent_registry.definition("generic-command")).compatible is False
