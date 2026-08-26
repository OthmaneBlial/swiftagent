"""ACP-first OpenCode transport selector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from swiftagent.agents.acp import AcpAdapter
from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.agents.opencode.json_adapter import OpenCodeJsonAdapter
from swiftagent.agents.opencode.status import detect_transport, resolve_cli_path
from swiftagent.models.task import Task

if TYPE_CHECKING:
    from swiftagent.agents.base import AgentAdapter
    from swiftagent.api.websocket import ConnectionManager


class OpenCodeAcpAdapter(AcpAdapter):
    """OpenCode-specific ACP policy layered on the shared stable client."""

    async def _authenticate(self, methods: list[Any]) -> None:
        # OpenCode owns its provider login state. Calling the advertised method
        # can launch an interactive login, which detection and task startup must
        # never trigger on the user's behalf.
        return None

    async def start(self) -> None:
        self.task.capability_snapshot.update(
            {
                "transport": "acp-v1",
                "session_sharing": False,
                "auth_owner": "opencode",
            }
        )
        await super().start()


class OpenCodeAdapter:
    """Expose one stable adapter while selecting the richest installed transport."""

    def __init__(self, task: Task, manager: ConnectionManager):
        self.task = task
        configured_model = task.config.model_id or opencode_settings.get_model()
        if configured_model and not task.config.model_id:
            task.config = task.config.model_copy(update={"model_id": configured_model})

        executable = resolve_cli_path()
        if not executable:
            raise RuntimeError("OpenCode was not found. Install it or configure its executable path.")
        transport = detect_transport(executable)
        if transport == "acp":
            workspace = task.config.working_directory
            command = [executable, "acp"]
            if workspace:
                command.extend(["--cwd", workspace])
            self._delegate: AgentAdapter = OpenCodeAcpAdapter(
                task,
                manager,
                command=command,
            )
        elif transport == "json":
            self._delegate = OpenCodeJsonAdapter(task, manager, executable=executable)
        else:
            raise RuntimeError(
                "This OpenCode installation exposes neither ACP nor `run --format json`."
            )

    @property
    def running(self) -> bool:
        return self._delegate.running

    @property
    def session_id(self) -> str | None:
        return self._delegate.session_id

    async def start(self) -> None:
        await self._delegate.start()

    async def wait(self) -> None:
        await self._delegate.wait()

    async def fail(self, error: str) -> None:
        await self._delegate.fail(error)

    async def cancel(self) -> None:
        await self._delegate.cancel()

    def dispose(self) -> None:
        self._delegate.dispose()
