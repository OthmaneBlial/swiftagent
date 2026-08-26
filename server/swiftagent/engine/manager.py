"""Task manager — orchestrates task lifecycle."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from swiftagent.engine.adapter import ClaudeAdapter
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.workspace import WorkspacePathError, resolve_workspace_path

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


class TaskManager:
    """Coordinates task execution and adapter lifecycle."""

    MAX_CONCURRENT = 5
    MAX_QUEUED = 25

    def __init__(self):
        self._active: dict[str, ClaudeAdapter] = {}
        self._queued: deque[ClaudeAdapter] = deque()
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
        task = Task(config=config, status=TaskStatus.RUNNING, session_id=session_id)

        user_msg = TaskMessage(role="user", content=config.prompt)
        task.messages.append(user_msg)

        task_repo.save_task(task)
        task_repo.add_task_message(task.id, user_msg)

        adapter = ClaudeAdapter(task, manager)
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

    async def _run_adapter(self, task_id: str, adapter: ClaudeAdapter) -> None:
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
            async with self._lock:
                self._active.pop(task_id, None)
            await self._start_next()

    async def _start_next(self) -> None:
        adapter: ClaudeAdapter | None = None
        async with self._lock:
            if self._queued and len(self._active) < self.MAX_CONCURRENT:
                adapter = self._queued.popleft()
                self._active[adapter.task.id] = adapter

        if adapter is not None:
            task_repo.update_task_status(adapter.task.id, TaskStatus.RUNNING)
            adapter.task.status = TaskStatus.RUNNING
            asyncio.create_task(self._run_adapter(adapter.task.id, adapter))

    async def cancel_task(self, task_id: str) -> None:
        queued_adapter: ClaudeAdapter | None = None
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
            return

        task = task_repo.get_task(task_id)
        if task is None:
            raise ValueError("Task not found")
        if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ValueError(f"Task is already {task.status.value}")
        task_repo.update_task_status(task_id, TaskStatus.CANCELLED, datetime.now(UTC))

    async def resume_session(
        self, session_id: str, prompt: str, manager: ConnectionManager
    ) -> Task:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            raise ValueError("Session id is required to resume a task")
        return await self._create_task(
            TaskConfig(prompt=prompt), manager, session_id=normalized_session_id
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
