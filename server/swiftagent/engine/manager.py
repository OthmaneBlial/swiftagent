"""Task manager — orchestrates task lifecycle."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from swiftagent.agents.base import AgentAdapter
from swiftagent.agents.registry import AgentRegistry, agent_registry
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.workspace import WorkspacePathError, get_workspace_dir, resolve_workspace_path

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


class TaskManager:
    """Coordinates task execution and adapter lifecycle."""

    MAX_CONCURRENT = 5
    MAX_QUEUED = 25

    def __init__(self, registry: AgentRegistry | None = None):
        self._registry = registry or agent_registry
        self._active: dict[str, AgentAdapter] = {}
        self._queued: deque[AgentAdapter] = deque()
        self._lock = asyncio.Lock()

    async def start_task(self, config: TaskConfig, manager: ConnectionManager) -> Task:
        return await self._create_task(config, manager)

    async def _create_task(
        self,
        config: TaskConfig,
        manager: ConnectionManager,
        *,
        session_id: str | None = None,
    ) -> Task:
        config = self._validate_config(config)
        definition = self._registry.definition(config.agent_id)
        task = Task(
            config=config,
            status=TaskStatus.RUNNING,
            agent_id=definition.agent_id,
            adapter_id=definition.adapter_id,
            adapter_version=definition.adapter_version,
            native_session_id=session_id,
            capability_snapshot={
                **definition.capabilities.model_dump(),
                "protocol": definition.protocol,
                "effective_sandbox_mode": settings_repo.get_sandbox_mode(),
            },
            session_id=session_id,
        )

        user_msg = TaskMessage(role="user", content=config.prompt)
        task.messages.append(user_msg)

        # Construct the adapter before persisting a running task so a broken
        # factory cannot leave an orphaned record behind.
        adapter = self._registry.create(config.agent_id, task, manager)

        task_repo.save_task(task)
        task_repo.add_task_message(task.id, user_msg)
        workspace = (
            Path(config.working_directory) if config.working_directory else get_workspace_dir()
        )
        baseline = await asyncio.to_thread(receipt_repo.capture_git_state, workspace)
        receipt_repo.initialize_receipt(task, workspace, baseline)

        should_start = False

        async with self._lock:
            if len(self._active) >= self.MAX_CONCURRENT:
                if len(self._queued) >= self.MAX_QUEUED:
                    task_repo.delete_task(task.id)
                    raise ValueError(
                        f"Task queue is full ({self.MAX_QUEUED} waiting). Wait for a task to finish and try again."
                    )
                task_repo.update_task_status(task.id, TaskStatus.QUEUED)
                task.status = TaskStatus.QUEUED
                self._queued.append(adapter)
                return task
            self._active[task.id] = adapter
            should_start = True

        if should_start:
            task_repo.update_task_status(task.id, TaskStatus.RUNNING)
            asyncio.create_task(self._run_adapter(task.id, adapter))
        return task

    @staticmethod
    def _validate_config(config: TaskConfig) -> TaskConfig:
        if not config.working_directory:
            return config
        try:
            working_directory = resolve_workspace_path(config.working_directory)
        except WorkspacePathError as exc:
            raise ValueError("Working directory must be inside the configured workspace") from exc
        if not working_directory.exists() or not working_directory.is_dir():
            raise ValueError("Working directory does not exist or is not a directory")
        return config.model_copy(update={"working_directory": str(working_directory)})

    async def _run_adapter(self, task_id: str, adapter: AgentAdapter) -> None:
        timeout_sec = int(os.environ.get("SWIFTAGENT_TASK_TIMEOUT_SEC", "900"))

        try:
            await adapter.start()
            await asyncio.wait_for(adapter.wait(), timeout=timeout_sec)
        except TimeoutError:
            await adapter.fail(f"Task timed out after {timeout_sec} seconds")
            await adapter.cancel()
        except Exception as e:
            print(f"[TaskManager] Task {task_id} error: {e}")
            await adapter.fail(str(e))
        finally:
            adapter.dispose()
            await self._finalize_receipt(task_id)
            async with self._lock:
                self._active.pop(task_id, None)
            await self._start_next()

    async def _start_next(self) -> None:
        adapter: AgentAdapter | None = None
        async with self._lock:
            if self._queued and len(self._active) < self.MAX_CONCURRENT:
                adapter = self._queued.popleft()
                self._active[adapter.task.id] = adapter

        if adapter is not None:
            task_repo.update_task_status(adapter.task.id, TaskStatus.RUNNING)
            adapter.task.status = TaskStatus.RUNNING
            asyncio.create_task(self._run_adapter(adapter.task.id, adapter))

    async def cancel_task(self, task_id: str) -> None:
        queued_adapter: AgentAdapter | None = None
        async with self._lock:
            adapter = self._active.pop(task_id, None)
            if adapter is None:
                for candidate in self._queued:
                    if candidate.task.id == task_id:
                        queued_adapter = candidate
                        break
                if queued_adapter is not None:
                    self._queued.remove(queued_adapter)

        if adapter:
            await adapter.cancel()
            return

        if queued_adapter:
            await queued_adapter.cancel()
            await self._finalize_receipt(task_id)
            return

        task = task_repo.get_task(task_id)
        if task is None:
            raise ValueError("Task not found")
        if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task is already {task.status.value}")
        task_repo.update_task_status(task_id, TaskStatus.CANCELLED, datetime.now(UTC))
        await self._finalize_receipt(task_id)

    @staticmethod
    async def _finalize_receipt(task_id: str) -> None:
        workspace = receipt_repo.get_pending_receipt_workspace(task_id)
        if workspace is None:
            return
        final_state = await asyncio.to_thread(receipt_repo.capture_git_state, workspace)
        receipt_repo.finalize_receipt(task_id, final_state)

    async def resume_session(
        self,
        session_id: str,
        prompt: str,
        manager: ConnectionManager,
        *,
        agent_id: str | None = None,
    ) -> Task:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("Session id is required to resume a task")
        source = task_repo.get_latest_task_by_native_session_id(normalized_session_id)
        selected_agent_id = source.agent_id if source is not None and agent_id is None else agent_id
        if selected_agent_id is None:
            raise ValueError("agent_id is required when the source native session is unavailable")
        if source is not None and source.agent_id != selected_agent_id:
            raise ValueError("Native sessions can only be resumed through their original agent")
        return await self._create_task(
            TaskConfig(
                prompt=prompt,
                agent_id=selected_agent_id,
                working_directory=source.config.working_directory if source else None,
                model_id=source.config.model_id if source else None,
            ),
            manager,
            session_id=normalized_session_id,
        )

    def get_active_task_ids(self) -> list[str]:
        return list(self._active.keys())

    async def shutdown(self) -> None:
        async with self._lock:
            active = list(self._active.values())
            queued = list(self._queued)
            self._active.clear()
            self._queued.clear()
        await asyncio.gather(
            *(adapter.cancel() for adapter in [*active, *queued]), return_exceptions=True
        )


task_manager = TaskManager()
