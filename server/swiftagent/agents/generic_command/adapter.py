"""Text-only subprocess adapter activated by a matching disposable-test receipt."""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from swiftagent.agents.generic_command import settings as generic_settings
from swiftagent.agents.generic_command.manifest import (
    allowed_environment,
    build_command,
    executable_identity,
    fingerprint,
    resolve_executable,
)
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import Task, TaskMessage, TaskResult, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.sandbox import wrap_command_for_sandbox
from swiftagent.tools.workspace import get_workspace_dir

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager

MAX_STDERR_BYTES = 65_536


class GenericCommandAdapter:
    """Run one reviewed literal command without shell interpolation."""

    def __init__(self, task: Task, manager: ConnectionManager):
        self.task = task
        self.manager = manager
        manifest = generic_settings.get_manifest()
        receipt = generic_settings.get_receipt()
        if manifest is None or receipt is None:
            raise RuntimeError("Generic command adapter has not passed its disposable test")
        executable = resolve_executable(manifest)
        if not executable:
            raise RuntimeError(f"Generic command executable was not found: {manifest.executable}")
        if receipt.manifest_fingerprint != fingerprint(manifest):
            raise RuntimeError("Generic command manifest changed after its disposable test")
        if receipt.executable_identity != executable_identity(executable):
            raise RuntimeError("Generic command executable changed after its disposable test")

        self._manifest = manifest
        self._receipt = receipt
        self._executable = executable
        self._process: asyncio.subprocess.Process | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._stdin: bytes | None = None
        self._stdout_parts: list[str] = []
        self._stdout_bytes = 0
        self._stderr = bytearray()
        self._completion_lock = asyncio.Lock()
        self._completed = False
        self._cancel_event = asyncio.Event()
        self._disposed = False

    @property
    def running(self) -> bool:
        return bool(
            self._process
            and self._process.returncode is None
            and self._run_task
            and not self._run_task.done()
            and not self._completed
        )

    @property
    def session_id(self) -> str | None:
        return None

    async def start(self) -> None:
        if self._disposed:
            raise RuntimeError("Adapter disposed")
        workspace = get_workspace_dir()
        task_directory = (
            Path(self.task.config.working_directory).resolve()
            if self.task.config.working_directory
            else workspace
        )
        cwd = task_directory if self._manifest.cwd_mode == "task" else workspace
        command, self._stdin = build_command(
            self._manifest,
            self._executable,
            self.task.config.prompt,
        )
        command, sandbox_notice = wrap_command_for_sandbox(
            command, cwd, settings_repo.get_sandbox_mode()
        )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if self._stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=allowed_environment(self._manifest),
            start_new_session=True,
        )
        self.task.capability_snapshot.update(
            {
                "transport": "literal-subprocess",
                "structured_streaming": False,
                "session_resume": False,
                "session_fork": False,
                "tool_events": False,
                "approvals": False,
                "questions": False,
                "plan_updates": False,
                "attachments": False,
                "model_discovery": False,
                "usage": False,
                "native_sandbox": False,
                "manifest_fingerprint": self._receipt.manifest_fingerprint,
                "disposable_tested_at": self._receipt.tested_at.isoformat(),
            }
        )
        task_repo.update_task_capability_snapshot(self.task.id, self.task.capability_snapshot)
        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_PROGRESS,
                task_id=self.task.id,
                payload={
                    "stage": "starting",
                    "message": f"Starting verified text adapter: {self._manifest.name}",
                    "sandbox_notice": sandbox_notice,
                },
            )
        )
        await self._emit(
            AgentEventType.RUN_STARTED,
            {
                "name": self._manifest.name,
                "transport": "literal-subprocess",
                "cwd": str(cwd),
                "prompt_transport": self._manifest.prompt_transport,
                "timeout_seconds": self._manifest.timeout_seconds,
                "sandbox_notice": sandbox_notice,
            },
            native_event_type="process.start",
        )
        self._run_task = asyncio.create_task(self._run_with_timeout())

    async def _run_with_timeout(self) -> None:
        try:
            await asyncio.wait_for(self._consume_process(), timeout=self._manifest.timeout_seconds)
        except TimeoutError:
            self._terminate_process()
            await self._wait_or_kill()
            await self._finish(
                TaskStatus.FAILED,
                success=False,
                error=f"Generic command timed out after {self._manifest.timeout_seconds} seconds",
                summary=self._summary(),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._terminate_process()
            await self._wait_or_kill()
            await self._finish(TaskStatus.FAILED, success=False, error=str(exc), summary=self._summary())

    async def _consume_process(self) -> None:
        assert self._process is not None
        if self._stdin is not None and self._process.stdin is not None:
            self._process.stdin.write(self._stdin)
            await self._process.stdin.drain()
            self._process.stdin.close()

        stdout_task = asyncio.create_task(self._read_stdout())
        stderr_task = asyncio.create_task(self._read_stderr())
        wait_task = asyncio.create_task(self._process.wait())
        try:
            await asyncio.gather(stdout_task, stderr_task, wait_task)
        except Exception:
            self._terminate_process()
            await self._wait_or_kill()
            for task in (stdout_task, stderr_task, wait_task):
                if not task.done():
                    task.cancel()
            raise
        returncode = wait_task.result()

        if self._cancel_event.is_set():
            await self._finish(
                TaskStatus.CANCELLED,
                success=False,
                error="Generic command cancelled",
                summary=self._summary(),
            )
            return
        if returncode != 0:
            diagnostics = self._stderr.decode("utf-8", errors="replace")[-4_096:]
            await self._finish(
                TaskStatus.FAILED,
                success=False,
                error=f"Generic command exited with code {returncode}: {diagnostics}",
                summary=self._summary(),
            )
            return
        await self._persist_message()
        await self._finish(TaskStatus.COMPLETED, success=True, summary=self._summary())

    async def _read_stdout(self) -> None:
        if not self._process or not self._process.stdout:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            chunk = await self._process.stdout.read(16_384)
            if not chunk:
                break
            self._stdout_bytes += len(chunk)
            if self._stdout_bytes > self._manifest.max_output_bytes:
                raise RuntimeError(
                    f"Generic command stdout exceeded {self._manifest.max_output_bytes} bytes"
                )
            text = decoder.decode(chunk)
            if text:
                self._stdout_parts.append(text)
                await self._emit(
                    AgentEventType.MESSAGE_DELTA,
                    {"message_id": "stdout", "role": "assistant", "content": text},
                    native_event_type="stdout.chunk",
                )
        tail = decoder.decode(b"", final=True)
        if tail:
            self._stdout_parts.append(tail)

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        while True:
            chunk = await self._process.stderr.read(16_384)
            if not chunk:
                return
            remaining = MAX_STDERR_BYTES - len(self._stderr)
            if remaining > 0:
                self._stderr.extend(chunk[:remaining])

    async def _persist_message(self) -> None:
        content = self._summary()
        if not content:
            return
        task_repo.add_task_message(
            self.task.id,
            TaskMessage(
                role="assistant",
                content=content,
                metadata={"protocol": "literal-subprocess", "stream": "stdout"},
            ),
        )
        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_MESSAGE,
                task_id=self.task.id,
                payload={"role": "assistant", "content": content},
            )
        )
        await self._emit(
            AgentEventType.MESSAGE_COMPLETED,
            {"message_id": "stdout", "role": "assistant", "content": content},
            native_event_type="stdout.complete",
        )

    def _summary(self) -> str | None:
        content = "".join(self._stdout_parts).strip()
        return content or None

    async def _finish(
        self,
        status: TaskStatus,
        *,
        success: bool,
        error: str | None = None,
        summary: str | None = None,
    ) -> None:
        async with self._completion_lock:
            if self._completed:
                return
            self._completed = True
            self.task.status = status
            self.task.completed_at = datetime.now(UTC)
            self.task.summary = summary
            self.task.result = TaskResult(success=success, error=error, summary=summary)
            task_repo.complete_task(self.task, self.task.result)
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_COMPLETE,
                    task_id=self.task.id,
                    payload={
                        "status": status.value,
                        "success": success,
                        "error": error,
                        "summary": summary,
                        "session_id": None,
                    },
                )
            )
            await self._emit(
                AgentEventType.RUN_FAILED
                if status is TaskStatus.FAILED
                else AgentEventType.RUN_COMPLETED,
                {"status": status.value, "success": success, "error": error, "summary": summary},
                native_event_type="process.exit",
            )

    async def wait(self) -> None:
        if self._run_task:
            await self._run_task

    async def fail(self, error: str) -> None:
        self._terminate_process()
        await self._wait_or_kill()
        await self._finish(TaskStatus.FAILED, success=False, error=error, summary=self._summary())

    async def cancel(self) -> None:
        self._cancel_event.set()
        self._terminate_process()
        await self._wait_or_kill()
        await self._finish(
            TaskStatus.CANCELLED,
            success=False,
            error="Generic command cancelled",
            summary=self._summary(),
        )

    async def _wait_or_kill(self) -> None:
        if not self._process or self._process.returncode is not None:
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=2)
        except TimeoutError:
            self._kill_process()
            with contextlib.suppress(Exception):
                await self._process.wait()

    def dispose(self) -> None:
        self._disposed = True
        self._terminate_process()

    def _terminate_process(self) -> None:
        if not self._process or self._process.returncode is not None:
            return
        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            self._process.terminate()

    def _kill_process(self) -> None:
        if not self._process or self._process.returncode is not None:
            return
        try:
            os.killpg(self._process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            self._process.kill()

    async def _emit(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any],
        *,
        native_event_type: str,
    ) -> None:
        await self.manager.broadcast_agent_event(
            AgentEvent(
                type=event_type,
                agent_id=self.task.agent_id,
                adapter_id=self.task.adapter_id,
                run_id=self.task.id,
                native_event_type=native_event_type,
                payload=payload,
            )
        )
