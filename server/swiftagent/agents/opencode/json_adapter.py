"""Reduced OpenCode `run --format json` fallback adapter."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from swiftagent.agents.acp.client import AcpClientBridge
from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import Task, TaskMessage, TaskResult, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.sandbox import wrap_command_for_sandbox
from swiftagent.tools.workspace import get_workspace_dir

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager

logger = logging.getLogger(__name__)
MAX_JSON_LINE_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 65_536


class OpenCodeJsonAdapter:
    """Maps the documented raw JSON event stream with deliberately reduced controls."""

    def __init__(self, task: Task, manager: ConnectionManager, *, executable: str):
        self.task = task
        self.manager = manager
        self._executable = executable
        self._process: asyncio.subprocess.Process | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr: list[str] = []
        self._stderr_bytes = 0
        self._session_id = task.native_session_id or task.session_id
        self._workspace: Path | None = None
        self._cancel_event = asyncio.Event()
        self._completion_lock = asyncio.Lock()
        self._completed = False
        self._disposed = False
        self._messages: dict[str, str] = {}
        self._message_order: list[str] = []
        self._tool_status: dict[str, str] = {}
        self._saw_event = False

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
        return self._session_id

    async def start(self) -> None:
        if self._disposed:
            raise RuntimeError("Adapter disposed")
        self._workspace = (
            Path(self.task.config.working_directory).resolve()
            if self.task.config.working_directory
            else get_workspace_dir()
        )
        model = self.task.config.model_id or opencode_settings.get_model()
        command = [
            self._executable,
            "run",
            "--format",
            "json",
            "--dir",
            str(self._workspace),
        ]
        if self._session_id:
            command.extend(["--session", self._session_id])
        if model:
            command.extend(["--model", model])
            self.task.capability_snapshot["effective_model"] = model
        for attachment in self.task.config.attachments:
            candidate = Path(attachment.path).expanduser()
            resolved = (
                candidate.resolve(strict=False)
                if candidate.is_absolute()
                else (self._workspace / candidate).resolve(strict=False)
            )
            if resolved != self._workspace and self._workspace not in resolved.parents:
                raise RuntimeError(f"OpenCode attachment escapes the selected workspace: {attachment.path}")
            if not resolved.is_file():
                raise RuntimeError(f"OpenCode attachment was not found: {attachment.path}")
            command.extend(["--file", str(resolved)])
        command.append(self.task.config.prompt)

        command, sandbox_notice = wrap_command_for_sandbox(
            command, self._workspace, settings_repo.get_sandbox_mode()
        )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workspace),
            env=os.environ.copy(),
            start_new_session=True,
            limit=MAX_JSON_LINE_BYTES + 1,
        )
        self.task.capability_snapshot.update(
            {
                "transport": "opencode-json-run",
                "structured_streaming": True,
                "session_resume": True,
                "session_fork": False,
                "tool_events": True,
                "approvals": False,
                "questions": False,
                "plan_updates": False,
                "attachments": True,
                "attachment_types": ["*/*"],
                "model_discovery": True,
                "usage": True,
                "native_sandbox": False,
                "limitations": [
                    "no interactive approvals",
                    "no questions",
                    "no plans",
                    "no native sandbox controls",
                    "no automatic session sharing",
                ],
            }
        )
        task_repo.update_task_capability_snapshot(self.task.id, self.task.capability_snapshot)
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_PROGRESS,
                task_id=self.task.id,
                payload={
                    "stage": "starting",
                    "message": "OpenCode reduced JSON-run mode started",
                    "sandbox_notice": sandbox_notice,
                },
            )
        )
        await self._emit(
            AgentEventType.RUN_STARTED,
            {
                "transport": "opencode-json-run",
                "workspace": str(self._workspace),
                "sandbox_notice": sandbox_notice,
                "interactive_approvals": False,
                "session_sharing": False,
            },
            native_event_type="process.start",
        )
        self._run_task = asyncio.create_task(self._run_stream())

    async def _run_stream(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_JSON_LINE_BYTES:
                    raise RuntimeError("OpenCode emitted a JSON event larger than 2 MiB")
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError("OpenCode emitted malformed JSON") from exc
                if not isinstance(event, dict):
                    raise RuntimeError("OpenCode emitted a non-object JSON event")
                self._saw_event = True
                await self._handle_event(event)

            returncode = await self._process.wait()
            if self._stderr_task:
                await self._stderr_task
            if self._cancel_event.is_set():
                await self._finish(
                    TaskStatus.CANCELLED,
                    success=False,
                    error="OpenCode JSON run cancelled",
                    summary=self._summary(),
                )
            elif returncode != 0:
                diagnostics = "\n".join(self._stderr)[-4_096:] or f"exit code {returncode}"
                await self._finish(
                    TaskStatus.FAILED,
                    success=False,
                    error=f"OpenCode JSON run failed: {diagnostics}",
                    summary=self._summary(),
                )
            elif not self._saw_event:
                await self._finish(
                    TaskStatus.FAILED,
                    success=False,
                    error="OpenCode JSON run exited without any structured event",
                )
            else:
                await self._flush_messages()
                await self._finish(
                    TaskStatus.COMPLETED,
                    success=True,
                    summary=self._summary(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._finish(TaskStatus.FAILED, success=False, error=str(exc))
            self._terminate_process()

    async def _handle_event(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "unknown")
        native_session = event.get("sessionID")
        if isinstance(native_session, str) and native_session:
            self._session_id = native_session
            self.task.native_session_id = native_session
            self.task.session_id = native_session
            task_repo.update_task_native_session_id(self.task.id, native_session)

        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event_type == "text":
            text = part.get("text")
            if not isinstance(text, str) or not text:
                return
            message_id = str(part.get("id") or part.get("messageID") or "opencode-message")
            previous = self._messages.get(message_id, "")
            if text == previous:
                return
            delta = text[len(previous) :] if previous and text.startswith(previous) else text
            self._messages[message_id] = text if text.startswith(previous) else previous + text
            if message_id not in self._message_order:
                self._message_order.append(message_id)
            await self._emit(
                AgentEventType.MESSAGE_DELTA,
                {"message_id": message_id, "role": "assistant", "content": delta},
                native_event_type="text",
                metadata=event,
            )
            return

        if event_type == "tool_use":
            tool_id = str(part.get("id") or part.get("callID") or "opencode-tool")
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            status = str(state.get("status") or part.get("status") or "pending")
            payload = {
                "tool_call_id": tool_id,
                "name": part.get("tool") or part.get("name") or "OpenCode tool",
                "status": status,
                "input": state.get("input") or part.get("input"),
                "output": state.get("output") or part.get("output"),
            }
            previous_status = self._tool_status.get(tool_id)
            self._tool_status[tool_id] = status
            terminal = status in {"completed", "failed", "error"}
            normalized_type = (
                AgentEventType.TOOL_COMPLETED
                if terminal
                else AgentEventType.TOOL_UPDATED
                if previous_status
                else AgentEventType.TOOL_STARTED
            )
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TOOL_RESULT if terminal else WSEventType.TOOL_USE,
                    task_id=self.task.id,
                    payload={**payload, "is_error": status in {"failed", "error"}},
                )
            )
            await self._emit(
                normalized_type,
                payload,
                native_event_type="tool_use",
                metadata=event,
            )
            return

        if event_type == "step_finish":
            tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
            await self._emit(
                AgentEventType.USAGE_UPDATED,
                {"tokens": tokens, "cost": part.get("cost"), "reason": part.get("reason")},
                native_event_type="step_finish",
                metadata=event,
            )
            return

        if event_type in {"error", "run_error"}:
            message = event.get("message") or part.get("message") or "OpenCode reported an error"
            raise RuntimeError(str(message)[:4_096])

        logger.debug("opencode_json_unknown task_id=%s event=%s", self.task.id, event_type)

    async def _flush_messages(self) -> None:
        for message_id in self._message_order:
            content = self._messages[message_id]
            if not content:
                continue
            task_repo.add_task_message(
                self.task.id,
                TaskMessage(
                    role="assistant",
                    content=content,
                    metadata={"message_id": message_id, "protocol": "opencode-json-run"},
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
                {"message_id": message_id, "role": "assistant", "content": content},
                native_event_type="process.flush",
            )

    def _summary(self) -> str | None:
        summary = "\n\n".join(self._messages[key] for key in self._message_order).strip()
        return summary or None

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
            self.task.native_session_id = self._session_id
            self.task.session_id = self._session_id
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
                        "session_id": self._session_id,
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

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        async for raw in self._process.stderr:
            if self._stderr_bytes >= MAX_STDERR_BYTES:
                continue
            self._stderr_bytes += len(raw)
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self._stderr.append(line[:2_048])
                logger.warning("opencode_json_stderr task_id=%s message=%s", self.task.id, line[:2_048])

    async def wait(self) -> None:
        if self._run_task:
            await self._run_task

    async def fail(self, error: str) -> None:
        await self._finish(TaskStatus.FAILED, success=False, error=error)
        self._terminate_process()

    async def cancel(self) -> None:
        self._cancel_event.set()
        self._terminate_process()
        if self._process and self._process.returncode is None:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except TimeoutError:
                self._kill_process()
                with contextlib.suppress(Exception):
                    await self._process.wait()
        await self._finish(
            TaskStatus.CANCELLED,
            success=False,
            error="OpenCode JSON run cancelled",
            summary=self._summary(),
        )

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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.manager.broadcast_agent_event(
            AgentEvent(
                type=event_type,
                agent_id=self.task.agent_id,
                adapter_id=self.task.adapter_id,
                run_id=self.task.id,
                native_session_id=self._session_id,
                native_event_type=native_event_type,
                payload=payload,
                native_metadata=AcpClientBridge.diagnostics(metadata or {}),
            )
        )
