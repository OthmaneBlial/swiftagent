from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swiftagent.agents.claude import ClaudeCodeAdapter
from swiftagent.agents.registry import AgentRegistry
from swiftagent.models.agent import AgentCapabilities, AgentDefinition
from swiftagent.models.task import Task, TaskConfig, TaskResult, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo


def test_terminal_result_survives_reload_and_restart_recovery(client):
    task = Task(config=TaskConfig(prompt="Summarize this project"), status=TaskStatus.RUNNING)
    task_repo.save_task(task)
    task.status = TaskStatus.COMPLETED
    task.summary = "A concise summary"
    task.result = TaskResult(success=True, summary=task.summary)
    task_repo.complete_task(task, task.result)

    reloaded = task_repo.get_task(task.id)
    assert reloaded is not None
    assert reloaded.result is not None
    assert reloaded.result.success is True
    assert reloaded.result.summary == "A concise summary"

    interrupted = Task(config=TaskConfig(prompt="Long running work"), status=TaskStatus.RUNNING)
    task_repo.save_task(interrupted)
    assert task_repo.recover_interrupted_tasks() == 1

    recovered = task_repo.get_task(interrupted.id)
    assert recovered is not None
    assert recovered.status is TaskStatus.FAILED
    assert recovered.result is not None
    assert "restarted" in (recovered.result.error or "")


@pytest.mark.asyncio
async def test_queued_task_starts_when_a_slot_becomes_available(client):
    import swiftagent.engine.manager as manager_module

    started = asyncio.Event()
    release = asyncio.Event()

    class FakeAdapter:
        def __init__(self, task, manager):
            self.task = task
            self.manager = manager

        async def start(self):
            started.set()

        async def wait(self):
            await release.wait()

        async def fail(self, error):
            raise AssertionError(error)

        async def cancel(self):
            self.task.status = TaskStatus.CANCELLED

        def dispose(self):
            pass

    registry = AgentRegistry()
    registry.register(
        AgentDefinition(
            agent_id="fake-agent",
            display_name="Fake Agent",
            adapter_id="fake-adapter",
            adapter_version="1.0.0",
            protocol="test",
            capabilities=AgentCapabilities(),
        ),
        FakeAdapter,
    )
    task_manager = manager_module.TaskManager(registry)
    task_manager.MAX_CONCURRENT = 1
    task_manager._active["occupied"] = object()  # Occupy the only slot without a subprocess.

    task = await task_manager.start_task(
        TaskConfig(prompt="Queued work", agent_id="fake-agent"), object()
    )
    assert task.status is TaskStatus.QUEUED
    assert task.agent_id == "fake-agent"
    assert task.adapter_id == "fake-adapter"
    assert task.adapter_version == "1.0.0"
    assert task.capability_snapshot["session_create"] is True
    assert len(task_manager._queued) == 1

    task_manager._active.clear()
    await task_manager._start_next()
    await asyncio.wait_for(started.wait(), timeout=1)
    assert task_manager.get_active_task_ids() == [task.id]

    release.set()
    await asyncio.sleep(0)


def test_strict_sandbox_never_silently_downgrades(client, monkeypatch):
    import swiftagent.agents.claude.adapter as adapter_module
    import swiftagent.storage.settings as app_settings

    adapter = ClaudeCodeAdapter(Task(config=TaskConfig(prompt="safe task")), manager=None)  # type: ignore[arg-type]
    monkeypatch.setattr(app_settings, "get_sandbox_mode", lambda: "strict")
    monkeypatch.setattr(adapter_module.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="Strict sandbox is unavailable"):
        adapter._build_command("claude", Path("/tmp"))


@pytest.mark.asyncio
async def test_resume_keeps_original_agent_workspace_and_model(client):
    from swiftagent.engine.manager import TaskManager

    workspace = Path(settings_repo.get_workspace_dir()) / "resume-fixture"
    workspace.mkdir(parents=True, exist_ok=True)
    source = Task(
        config=TaskConfig(
            prompt="Original run",
            agent_id="fixture-agent",
            working_directory=str(workspace),
            model_id="fixture-model",
        ),
        status=TaskStatus.COMPLETED,
        agent_id="fixture-agent",
        adapter_id="fixture-adapter",
        adapter_version="1.0.0",
        native_session_id="fixture-session",
        session_id="fixture-session",
        capability_snapshot={"session_resume": True},
    )
    task_repo.save_task(source)

    done = asyncio.Event()

    class ResumeAdapter:
        def __init__(self, task, manager):
            self.task = task
            self.manager = manager
            self.running = False
            self.session_id = task.session_id

        async def start(self):
            self.running = True

        async def wait(self):
            self.running = False
            self.task.status = TaskStatus.COMPLETED
            self.task.completed_at = datetime.now(UTC)
            self.task.result = TaskResult(success=True, summary="resumed")
            task_repo.complete_task(self.task, self.task.result)
            done.set()

        async def fail(self, error):
            raise AssertionError(error)

        async def cancel(self):
            return None

        def dispose(self):
            return None

    registry = AgentRegistry()
    registry.register(
        AgentDefinition(
            agent_id="fixture-agent",
            display_name="Fixture agent",
            adapter_id="fixture-adapter",
            adapter_version="1.0.0",
            protocol="fixture",
            capabilities=AgentCapabilities(session_resume=True),
        ),
        ResumeAdapter,
    )
    task_manager = TaskManager(registry)
    resumed = await task_manager.resume_session(
        "fixture-session",
        "Continue safely",
        object(),
    )
    await asyncio.wait_for(done.wait(), timeout=1)

    assert resumed.config.working_directory == str(workspace)
    assert resumed.config.model_id == "fixture-model"
    assert resumed.agent_id == "fixture-agent"

    with pytest.raises(ValueError, match="original agent"):
        await task_manager.resume_session(
            "fixture-session",
            "Do not cross native formats",
            object(),
            agent_id="different-agent",
        )
