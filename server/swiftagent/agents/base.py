"""Runtime contract implemented by every coding-agent adapter."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from swiftagent.models.task import Task


@runtime_checkable
class AgentAdapter(Protocol):
    """The task manager's only dependency on an agent implementation."""

    task: Task

    @property
    def running(self) -> bool: ...

    @property
    def session_id(self) -> str | None: ...

    async def start(self) -> None: ...

    async def wait(self) -> None: ...

    async def fail(self, error: str) -> None: ...

    async def cancel(self) -> None: ...

    def dispose(self) -> None: ...
