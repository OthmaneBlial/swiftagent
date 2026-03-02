"""Claude CLI adapter — process lifecycle and stream event mapping."""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import TYPE_CHECKING

from swiftagent.engine.parser import MessageType, ParsedMessage, StreamParser
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import Task, TaskMessage, TaskResult, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.workspace import get_workspace_dir

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


class ClaudeAdapter:
    """Manages a Claude CLI subprocess for one task."""

    def __init__(self, task: Task, manager: ConnectionManager):
        self.task = task
        self.manager = manager
        self._process: asyncio.subprocess.Process | None = None
        self._disposed = False

        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._wait_task: asyncio.Task | None = None

        self._session_id: str | None = task.session_id
        self._parser = StreamParser(self._handle_message)

        self._completion_lock = asyncio.Lock()
        self._completed = False
        self._saw_result = False

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None and not self._completed

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def start(self) -> None:
        if self._disposed:
            raise RuntimeError("Adapter disposed")

        claude_path = self._find_claude_cli()
        if not claude_path:
            raise RuntimeError("Claude CLI not found. Install Claude Code first.")

        workspace = get_workspace_dir()
        env = self._build_env()
        command = self._build_command(claude_path, workspace)

        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_PROGRESS,
                task_id=self.task.id,
                payload={
                    "stage": "starting",
                    "message": "Spawning Claude...",
                    "workspace": str(workspace),
                },
            )
        )

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(workspace),
        )

        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        self._wait_task = asyncio.create_task(self._wait_for_exit())

    async def wait(self) -> None:
        if self._wait_task:
            await self._wait_task

    async def fail(self, error: str) -> None:
        await self._complete_task(success=False, error=error)

    async def _wait_for_exit(self) -> None:
        assert self._process is not None

        returncode = await self._process.wait()

        if self._stdout_task:
            try:
                await asyncio.wait_for(self._stdout_task, timeout=3)
            except asyncio.TimeoutError:
                pass

        if self._completed:
            return

        if self._saw_result:
            # Give the result handler a short window to win the completion race.
            for _ in range(20):
                if self._completed:
                    return
                await asyncio.sleep(0.05)

        if returncode != 0:
            await self._complete_task(
                success=False,
                error=f"Claude process exited with code {returncode}",
            )
            return

        await self._complete_task(
            success=False,
            error="Claude process exited before emitting a result event",
        )

    async def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            async for line in self._process.stdout:
                if self._disposed:
                    break
                self._parser.feed(line.decode("utf-8", errors="replace"))
        finally:
            self._parser.flush()

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            async for line in self._process.stderr:
                if self._disposed:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    print(f"[Claude stderr] {text}")
        except Exception:
            pass

    def _handle_message(self, msg: ParsedMessage) -> None:
        asyncio.create_task(self._handle_message_async(msg))

    async def _handle_message_async(self, msg: ParsedMessage) -> None:
        if msg.type == MessageType.SESSION_ID:
            self._session_id = msg.content
            task_repo.update_task_session_id(self.task.id, msg.content)
            return

        if msg.type == MessageType.TEXT:
            task_msg = TaskMessage(role="assistant", content=msg.content)
            task_repo.add_task_message(self.task.id, task_msg)
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_MESSAGE,
                    task_id=self.task.id,
                    payload={"role": "assistant", "content": msg.content},
                )
            )
            return

        if msg.type == MessageType.TOOL_USE:
            tool_name = msg.data.get("name") or msg.content
            tool_input = msg.data.get("input") or {}
            tool_use_id = msg.data.get("tool_use_id")

            task_repo.add_task_message(
                self.task.id,
                TaskMessage(
                    role="tool",
                    content=f"Using tool: {tool_name}",
                    metadata={
                        "kind": "tool_use",
                        "tool_use_id": tool_use_id,
                        "name": tool_name,
                        "input": tool_input,
                    },
                ),
            )
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TOOL_USE,
                    task_id=self.task.id,
                    payload={
                        "name": tool_name,
                        "input": tool_input,
                        "tool_use_id": tool_use_id,
                    },
                )
            )
            return

        if msg.type == MessageType.TOOL_RESULT:
            tool_use_id = msg.data.get("tool_use_id")
            is_error = bool(msg.data.get("is_error"))

            task_repo.add_task_message(
                self.task.id,
                TaskMessage(
                    role="tool",
                    content=msg.content,
                    metadata={
                        "kind": "tool_result",
                        "tool_use_id": tool_use_id,
                        "is_error": is_error,
                    },
                ),
            )
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TOOL_RESULT,
                    task_id=self.task.id,
                    payload={
                        "content": msg.content,
                        "tool_use_id": tool_use_id,
                        "is_error": is_error,
                    },
                )
            )
            return

        if msg.type == MessageType.ERROR:
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_ERROR,
                    task_id=self.task.id,
                    payload={"error": msg.content},
                )
            )
            return

        if msg.type == MessageType.RESULT:
            self._saw_result = True
            if msg.data.get("session_id"):
                self._session_id = str(msg.data["session_id"])
                task_repo.update_task_session_id(self.task.id, self._session_id)

            await self._complete_task(
                success=bool(msg.data.get("success", True)),
                error=msg.data.get("error"),
                summary=msg.data.get("result") if msg.data.get("success", True) else None,
            )

    async def _complete_task(
        self,
        success: bool,
        error: str | None = None,
        summary: str | None = None,
    ) -> None:
        async with self._completion_lock:
            if self._completed:
                return
            self._completed = True

            now = datetime.now(UTC)
            status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            result = TaskResult(success=success, error=error, summary=summary)

            task_repo.update_task_status(self.task.id, status, now)
            if summary:
                task_repo.update_task_summary(self.task.id, summary)
            if self._session_id:
                task_repo.update_task_session_id(self.task.id, self._session_id)

            self.task.status = status
            self.task.result = result
            self.task.completed_at = now
            self.task.summary = summary
            self.task.session_id = self._session_id

            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_COMPLETE,
                    task_id=self.task.id,
                    payload={
                        "status": status.value,
                        "success": success,
                        "error": error,
                        "summary": summary,
                        "session_id": self._session_id,
                    },
                )
            )

    async def cancel(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()

        async with self._completion_lock:
            if self._completed:
                return
            self._completed = True

            now = datetime.now(UTC)
            task_repo.update_task_status(self.task.id, TaskStatus.CANCELLED, now)
            self.task.status = TaskStatus.CANCELLED
            self.task.completed_at = now

        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_COMPLETE,
                task_id=self.task.id,
                payload={
                    "status": TaskStatus.CANCELLED.value,
                    "success": False,
                    "error": "Task cancelled",
                    "session_id": self._session_id,
                },
            )
        )

    def dispose(self) -> None:
        self._disposed = True
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass

    # ── command building ───────────────────────────────────────

    def _find_claude_cli(self) -> str | None:
        configured = settings_repo.get_claude_cli_path()
        if configured:
            return configured
        return shutil.which("claude")

    def _build_claude_args(self) -> list[str]:
        args = ["-p", "--verbose", "--output-format", "stream-json"]

        model = self.task.config.model_id or settings_repo.get_claude_model()
        if model:
            args.extend(["--model", model])

        permission_mode = settings_repo.get_claude_permission_mode()
        if permission_mode:
            args.extend(["--permission-mode", permission_mode])

        if self._session_id:
            args.extend(["-r", self._session_id])

        args.append(self.task.config.prompt)
        return args

    def _build_command(self, claude_path: str, workspace: Path) -> list[str]:
        args = self._build_claude_args()

        sandbox_mode = settings_repo.get_sandbox_mode()
        bwrap_path = shutil.which("bwrap")
        if sandbox_mode == "strict" and bwrap_path:
            claude_dir = Path.home() / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)

            return [
                bwrap_path,
                "--die-with-parent",
                "--ro-bind",
                "/",
                "/",
                "--dev-bind",
                "/dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--bind",
                str(workspace),
                str(workspace),
                "--bind",
                str(claude_dir),
                str(claude_dir),
                "--chdir",
                str(workspace),
                "--setenv",
                "HOME",
                str(Path.home()),
                claude_path,
                *args,
            ]

        return [claude_path, *args]

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        return env
