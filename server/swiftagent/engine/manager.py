"""
Task manager — orchestrates task lifecycle.

Ported from base/accomplish/packages/agent-core/src/internal/classes/TaskManager.ts
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from swiftagent.engine.adapter import OpenCodeAdapter
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import tasks as task_repo

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


class TaskManager:
    """
    Manages concurrent task execution.

    Coordinates OpenCodeAdapter instances, handles queuing,
    and provides a clean API for task operations.
    """

    MAX_CONCURRENT = 5

    def __init__(self):
        self._active: dict[str, OpenCodeAdapter] = {}
        self._lock = asyncio.Lock()

    async def start_task(self, config: TaskConfig, manager: ConnectionManager) -> Task:
        """Start a new task."""
        task = Task(config=config, status=TaskStatus.RUNNING)

        # Save user prompt as first message
        user_msg = TaskMessage(role="user", content=config.prompt)
        task.messages.append(user_msg)

        # Persist
        task_repo.save_task(task)
        task_repo.add_task_message(task.id, user_msg)

        # Check capacity
        if len(self._active) >= self.MAX_CONCURRENT:
            task_repo.update_task_status(task.id, TaskStatus.QUEUED)
            task.status = TaskStatus.QUEUED
            return task

        # Execute
        adapter = OpenCodeAdapter(task, manager)
        self._active[task.id] = adapter

        task_repo.update_task_status(task.id, TaskStatus.RUNNING)

        # Start in background
        asyncio.create_task(self._run_adapter(task.id, adapter))

        return task

    async def _run_adapter(self, task_id: str, adapter: OpenCodeAdapter) -> None:
        """Run an adapter and clean up when done."""
        try:
            await adapter.start()
            # Wait for process to finish
            if adapter._process:
                await adapter._process.wait()
        except Exception as e:
            print(f"[TaskManager] Task {task_id} error: {e}")
            task_repo.update_task_status(task_id, TaskStatus.FAILED, datetime.utcnow())
        finally:
            adapter.dispose()
            async with self._lock:
                self._active.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a running task."""
        adapter = self._active.get(task_id)
        if adapter:
            await adapter.cancel()
            adapter.dispose()
            async with self._lock:
                self._active.pop(task_id, None)
        else:
            # Task may be in DB but not running
            task_repo.update_task_status(task_id, TaskStatus.CANCELLED, datetime.utcnow())

    async def resume_session(
        self, session_id: str, prompt: str, manager: ConnectionManager
    ) -> Task:
        """Resume a previous session with a new prompt."""
        config = TaskConfig(prompt=prompt)
        task = Task(config=config, status=TaskStatus.RUNNING, session_id=session_id)

        task_repo.save_task(task)

        adapter = OpenCodeAdapter(task, manager)
        self._active[task.id] = adapter
        asyncio.create_task(self._run_adapter(task.id, adapter))

        return task

    def get_active_task_ids(self) -> list[str]:
        return list(self._active.keys())

    def dispose_all(self) -> None:
        """Dispose all active adapters."""
        for adapter in self._active.values():
            adapter.dispose()
        self._active.clear()


# Singleton
task_manager = TaskManager()
