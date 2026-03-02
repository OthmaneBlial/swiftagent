"""Task manager — orchestrates task lifecycle."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, UTC
from typing import TYPE_CHECKING

from swiftagent.engine.adapter import ClaudeAdapter
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskStatus
from swiftagent.storage import tasks as task_repo

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


class TaskManager:
    """Coordinates task execution and adapter lifecycle."""

    MAX_CONCURRENT = 5

    def __init__(self):
        self._active: dict[str, ClaudeAdapter] = {}
        self._lock = asyncio.Lock()

    async def start_task(self, config: TaskConfig, manager: ConnectionManager) -> Task:
        task = Task(config=config, status=TaskStatus.RUNNING)

        user_msg = TaskMessage(role="user", content=config.prompt)
        task.messages.append(user_msg)

        task_repo.save_task(task)
        task_repo.add_task_message(task.id, user_msg)

        adapter = ClaudeAdapter(task, manager)

        async with self._lock:
            if len(self._active) >= self.MAX_CONCURRENT:
                task_repo.update_task_status(task.id, TaskStatus.QUEUED)
                task.status = TaskStatus.QUEUED
                return task
            self._active[task.id] = adapter

        task_repo.update_task_status(task.id, TaskStatus.RUNNING)

        asyncio.create_task(self._run_adapter(task.id, adapter))
        return task

    async def _run_adapter(self, task_id: str, adapter: ClaudeAdapter) -> None:
        timeout_sec = int(os.environ.get("SWIFTAGENT_TASK_TIMEOUT_SEC", "900"))

        try:
            await adapter.start()
            await asyncio.wait_for(adapter.wait(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            await adapter.fail(f"Task timed out after {timeout_sec} seconds")
            await adapter.cancel()
        except Exception as e:
            print(f"[TaskManager] Task {task_id} error: {e}")
            await adapter.fail(str(e))
        finally:
            adapter.dispose()
            async with self._lock:
                self._active.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> None:
        async with self._lock:
            adapter = self._active.pop(task_id, None)

        if adapter:
            await adapter.cancel()
            adapter.dispose()
        else:
            task_repo.update_task_status(task_id, TaskStatus.CANCELLED, datetime.now(UTC))

    async def resume_session(
        self, session_id: str, prompt: str, manager: ConnectionManager
    ) -> Task:
        config = TaskConfig(prompt=prompt)
        task = Task(config=config, status=TaskStatus.RUNNING, session_id=session_id)

        user_msg = TaskMessage(role="user", content=prompt)
        task.messages.append(user_msg)

        task_repo.save_task(task)
        task_repo.add_task_message(task.id, user_msg)

        adapter = ClaudeAdapter(task, manager)
        async with self._lock:
            self._active[task.id] = adapter
        task_repo.update_task_status(task.id, TaskStatus.RUNNING)
        asyncio.create_task(self._run_adapter(task.id, adapter))

        return task

    def get_active_task_ids(self) -> list[str]:
        return list(self._active.keys())

    def dispose_all(self) -> None:
        for adapter in self._active.values():
            adapter.dispose()
        self._active.clear()


task_manager = TaskManager()
