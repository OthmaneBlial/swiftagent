from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from swiftagent.agents.registry import AgentRegistry
from swiftagent.models.agent import (
    AgentCapabilities,
    AgentDefinition,
    AgentEvent,
    AgentEventType,
    AgentStatus,
)
from swiftagent.models.task import Task, TaskConfig, TaskResult, TaskStatus
from swiftagent.storage import tasks as task_repo
from swiftagent.storage.database import _migrate_v1, _migrate_v2, _migrate_v3


class NoopAdapter:
    def __init__(self, task, manager):
        self.task = task
        self.manager = manager
        self.session_id = task.native_session_id
        self.running = False

    async def start(self):
        return None

    async def wait(self):
        return None

    async def fail(self, error):
        raise AssertionError(error)

    async def cancel(self):
        return None

    def dispose(self):
        return None


def _test_definition(agent_id: str = "fixture-agent") -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent_id,
        display_name="Fixture Agent",
        adapter_id="fixture-adapter",
        adapter_version="1.2.3",
        protocol="fixture-json",
        capabilities=AgentCapabilities(
            structured_streaming=True,
            session_resume=True,
            tool_events=True,
            external_sandbox="verified",
        ),
    )


def test_agent_registry_rejects_duplicates_and_unknown_agents():
    registry = AgentRegistry()
    definition = _test_definition()
    registry.register(definition, NoopAdapter)

    assert registry.definition("fixture-agent") == definition
    assert registry.create(
        "fixture-agent",
        Task(config=TaskConfig(prompt="hello", agent_id="fixture-agent")),
        object(),
    ).task.config.agent_id == "fixture-agent"

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition, NoopAdapter)
    with pytest.raises(ValueError, match="Unknown agent 'missing-agent'"):
        registry.definition("missing-agent")


def test_agent_registry_status_cache_and_capability_combinations():
    registry = AgentRegistry()
    calls: list[str] = []
    combinations = [
        AgentCapabilities(structured_streaming=True, tool_events=True, session_resume=True),
        AgentCapabilities(structured_streaming=True, approvals=True, questions=True),
        AgentCapabilities(structured_streaming=False, external_sandbox="unsupported"),
    ]

    for index, capabilities in enumerate(combinations):
        definition = AgentDefinition(
            agent_id=f"fixture-{index}",
            display_name=f"Fixture {index}",
            adapter_id=f"adapter-{index}",
            adapter_version="1.0.0",
            protocol="fixture",
            capabilities=capabilities,
        )

        def provider(current, *, _index=index):
            calls.append(current.agent_id)
            return AgentStatus(
                **current.model_dump(),
                installed=_index != 2,
                compatible=None if _index == 0 else _index == 1,
            )

        registry.register(definition, NoopAdapter, provider)

    first = registry.statuses()
    second = registry.statuses()
    refreshed = registry.statuses(refresh=True)

    assert len(first) == len(second) == len(refreshed) == 3
    assert len(calls) == 6
    assert first[0].capabilities.session_resume is True
    assert first[1].capabilities.approvals is True
    assert first[2].capabilities.structured_streaming is False


def test_agents_endpoint_and_default_agent_setting(client, monkeypatch):
    import swiftagent.api.routes as routes_module

    definition = _test_definition("fixture-agent")
    status = AgentStatus(
        **definition.model_dump(),
        installed=True,
        compatible=True,
        executable_path="/opt/tools/fixture",
        auth_status="ready",
    )
    monkeypatch.setattr(routes_module.agent_registry, "statuses", lambda **_: [status])

    response = client.get("/api/agents?refresh=true")

    assert response.status_code == 200
    assert response.json()["agents"][0]["agent_id"] == "fixture-agent"
    assert response.json()["agents"][0]["capabilities"]["tool_events"] is True

    unknown = client.put("/api/settings", json={"default_agent_id": "missing-agent"})
    assert unknown.status_code == 400

    updated = client.put("/api/settings", json={"default_agent_id": "claude-code"})
    assert updated.status_code == 200
    assert updated.json()["default_agent_id"] == "claude-code"


@pytest.mark.asyncio
async def test_fake_adapter_runs_completes_cancels_and_persists_without_claude(client):
    from swiftagent.engine.manager import TaskManager

    completed = asyncio.Event()
    started = asyncio.Event()

    class RecordingManager:
        def __init__(self):
            self.events = []

        async def broadcast_agent_event(self, event):
            self.events.append(event)

    class LifecycleAdapter:
        def __init__(self, task, manager):
            self.task = task
            self.manager = manager
            self.session_id = None
            self.running = False
            self._release = asyncio.Event()
            self._cancelled = False

        async def start(self):
            self.running = True
            started.set()
            await self.manager.broadcast_agent_event(
                AgentEvent(
                    type=AgentEventType.RUN_STARTED,
                    agent_id=self.task.agent_id,
                    adapter_id=self.task.adapter_id,
                    run_id=self.task.id,
                )
            )

        async def wait(self):
            if self.task.config.prompt == "wait for cancellation":
                await self._release.wait()
            if self._cancelled:
                return
            self.running = False
            self.task.status = TaskStatus.COMPLETED
            self.task.result = TaskResult(success=True, summary="fixture complete")
            self.task.summary = "fixture complete"
            task_repo.complete_task(self.task, self.task.result)
            await self.manager.broadcast_agent_event(
                AgentEvent(
                    type=AgentEventType.RUN_COMPLETED,
                    agent_id=self.task.agent_id,
                    adapter_id=self.task.adapter_id,
                    run_id=self.task.id,
                )
            )
            completed.set()

        async def fail(self, error):
            raise AssertionError(error)

        async def cancel(self):
            self._cancelled = True
            self.running = False
            self.task.status = TaskStatus.CANCELLED
            self.task.result = TaskResult(success=False, error="cancelled by fixture")
            task_repo.complete_task(self.task, self.task.result)
            self._release.set()

        def dispose(self):
            self.running = False

    registry = AgentRegistry()
    registry.register(_test_definition("fixture-agent"), LifecycleAdapter)
    manager = RecordingManager()
    task_manager = TaskManager(registry)

    task = await task_manager.start_task(
        TaskConfig(prompt="finish normally", agent_id="fixture-agent"), manager
    )
    await asyncio.wait_for(completed.wait(), timeout=1)
    persisted = task_repo.get_task(task.id)

    assert persisted is not None
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.agent_id == "fixture-agent"
    assert [event.type for event in manager.events] == [
        AgentEventType.RUN_STARTED,
        AgentEventType.RUN_COMPLETED,
    ]

    started.clear()
    cancelled_task = await task_manager.start_task(
        TaskConfig(prompt="wait for cancellation", agent_id="fixture-agent"), manager
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    await task_manager.cancel_task(cancelled_task.id)
    await asyncio.sleep(0)

    cancelled = task_repo.get_task(cancelled_task.id)
    assert cancelled is not None
    assert cancelled.status is TaskStatus.CANCELLED
    assert cancelled.result is not None
    assert cancelled.result.error == "cancelled by fixture"


def test_normalized_agent_event_keeps_native_identity_and_metadata():
    event = AgentEvent(
        type=AgentEventType.TOOL_STARTED,
        agent_id="fixture-agent",
        adapter_id="fixture-adapter",
        run_id="run-1",
        native_session_id="native-1",
        native_event_type="content_block_start",
        payload={"name": "Read"},
        native_metadata={"tool_call_id": "tool-1"},
    )

    serialized = event.model_dump(mode="json")
    assert serialized["schema_version"] == 1
    assert serialized["type"] == "tool.started"
    assert serialized["native_session_id"] == "native-1"
    assert serialized["native_metadata"] == {"tool_call_id": "tool-1"}


def test_task_storage_round_trip_preserves_agent_identity_and_capabilities(client):
    definition = _test_definition()
    task = Task(
        config=TaskConfig(prompt="Inspect safely", agent_id=definition.agent_id),
        agent_id=definition.agent_id,
        adapter_id=definition.adapter_id,
        adapter_version=definition.adapter_version,
        native_session_id="native-session-1",
        session_id="native-session-1",
        capability_snapshot=definition.capabilities.model_dump(),
    )

    task_repo.save_task(task)
    reloaded = task_repo.get_task(task.id)

    assert reloaded is not None
    assert reloaded.agent_id == "fixture-agent"
    assert reloaded.adapter_id == "fixture-adapter"
    assert reloaded.adapter_version == "1.2.3"
    assert reloaded.native_session_id == "native-session-1"
    assert reloaded.session_id == "native-session-1"
    assert reloaded.capability_snapshot["tool_events"] is True
    assert reloaded.config.agent_id == "fixture-agent"


def test_v3_migration_marks_legacy_tasks_as_claude_without_losing_sessions():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    _migrate_v1(db)
    _migrate_v2(db)
    created_at = datetime.now(UTC).isoformat()
    config_json = json.dumps({"prompt": "Legacy task"})
    db.execute(
        """
        INSERT INTO tasks (
            id, prompt, working_directory, status, session_id, summary,
            result_json, config_json, created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-task",
            "Legacy task",
            None,
            "completed",
            "legacy-session",
            "done",
            None,
            config_json,
            created_at,
            created_at,
        ),
    )

    _migrate_v3(db)
    row = db.execute("SELECT * FROM tasks WHERE id = 'legacy-task'").fetchone()

    assert row["agent_id"] == "claude-code"
    assert row["adapter_id"] == "claude-stream-json"
    assert row["adapter_version"] == "0.3.0"
    assert row["native_session_id"] == "legacy-session"
    assert row["capability_snapshot_json"] == "{}"
