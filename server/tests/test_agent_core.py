from __future__ import annotations

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
)
from swiftagent.models.task import Task, TaskConfig
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
