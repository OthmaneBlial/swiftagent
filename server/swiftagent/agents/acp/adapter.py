"""ACP v1 adapter backed by the official Python SDK."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.connection import StreamEvent
from acp.schema import (
    AuthCapabilities,
    AuthMethodTerminal,
    ClientCapabilities,
    FileSystemCapabilities,
    Implementation,
)
from pydantic import BaseModel

from swiftagent.agents.acp import settings as acp_settings
from swiftagent.agents.acp.client import AcpClientBridge
from swiftagent.models.agent import AgentEvent, AgentEventType
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import Task, TaskMessage, TaskResult, TaskStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.sandbox import wrap_command_for_sandbox
from swiftagent.tools.workspace import get_workspace_dir

if TYPE_CHECKING:
    from acp.client.connection import ClientSideConnection

    from swiftagent.api.websocket import ConnectionManager

logger = logging.getLogger(__name__)
MAX_ACP_FRAME_BYTES = 2 * 1024 * 1024


class AcpAdapter:
    """Runs one local ACP v1 subprocess and translates its typed stream."""

    def __init__(
        self,
        task: Task,
        manager: ConnectionManager,
        *,
        command: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ):
        self.task = task
        self.manager = manager
        self._command = command
        self._environment = environment
        self._process: asyncio.subprocess.Process | None = None
        self._connection: ClientSideConnection | None = None
        self._bridge: AcpClientBridge | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._prompt_task: asyncio.Task[None] | None = None
        self._workspace: Path | None = None
        self._session_id = task.native_session_id or task.session_id
        self._cancel_event = asyncio.Event()
        self._completion_lock = asyncio.Lock()
        self._completed = False
        self._disposed = False
        self._message_chunks: dict[str, list[str]] = {}
        self._message_order: list[str] = []

    @property
    def running(self) -> bool:
        return bool(
            self._process
            and self._process.returncode is None
            and self._prompt_task
            and not self._prompt_task.done()
            and not self._completed
        )

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def cancel_event(self) -> asyncio.Event:
        return self._cancel_event

    async def start(self) -> None:
        if self._disposed:
            raise RuntimeError("Adapter disposed")
        configured = self._command or acp_settings.get_command()
        if not configured:
            raise RuntimeError(
                "No ACP command configured. Set SWIFTAGENT_ACP_COMMAND_JSON to a literal argv array."
            )

        self._workspace = (
            Path(self.task.config.working_directory).resolve()
            if self.task.config.working_directory
            else get_workspace_dir()
        )
        command, sandbox_notice = wrap_command_for_sandbox(
            configured, self._workspace, settings_repo.get_sandbox_mode()
        )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workspace),
            env=self._environment if self._environment is not None else os.environ.copy(),
            start_new_session=True,
            limit=MAX_ACP_FRAME_BYTES,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("ACP subprocess did not expose stdio")
        self._stderr_task = asyncio.create_task(self._read_stderr())
        self._bridge = AcpClientBridge(self, self._workspace)
        self._connection = connect_to_agent(
            self._bridge,
            self._process.stdin,
            self._process.stdout,
            observers=[self._observe_stream],
        )

        initialized = await asyncio.wait_for(
            self._connection.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(
                    fs=FileSystemCapabilities(readTextFile=True, writeTextFile=True),
                    terminal=True,
                    auth=AuthCapabilities(terminal=False),
                    elicitation=None,
                ),
                client_info=Implementation(
                    name="swiftagent",
                    title="SwiftAgent",
                    version="0.4.0-dev",
                ),
            ),
            timeout=15,
        )
        if initialized.protocol_version != PROTOCOL_VERSION:
            raise RuntimeError(
                f"ACP protocol mismatch: agent selected v{initialized.protocol_version}, "
                f"SwiftAgent supports v{PROTOCOL_VERSION}"
            )
        await self._authenticate(initialized.auth_methods or [])
        self._apply_capabilities(initialized.agent_capabilities)

        if self._session_id:
            if not self.task.capability_snapshot.get("session_resume"):
                raise RuntimeError("This ACP agent did not advertise session loading or resume")
            session_state = await asyncio.wait_for(
                self._connection.load_session(
                    cwd=str(self._workspace),
                    session_id=self._session_id,
                    mcp_servers=[],
                ),
                timeout=15,
            )
        else:
            session_state = await asyncio.wait_for(
                self._connection.new_session(cwd=str(self._workspace), mcp_servers=[]),
                timeout=15,
            )
            self._session_id = session_state.session_id

        await self._apply_session_config(session_state)
        if getattr(session_state, "modes", None):
            self.task.capability_snapshot["mode_discovery"] = True
        self.task.native_session_id = self._session_id
        self.task.session_id = self._session_id
        task_repo.update_task_native_session_id(self.task.id, self._session_id)
        task_repo.update_task_capability_snapshot(self.task.id, self.task.capability_snapshot)

        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_PROGRESS,
                task_id=self.task.id,
                payload={
                    "stage": "starting",
                    "message": "ACP session negotiated",
                    "workspace": str(self._workspace),
                    "sandbox_notice": sandbox_notice,
                },
            )
        )
        await self.emit_event(
            AgentEventType.RUN_STARTED,
            {
                "protocol_version": initialized.protocol_version,
                "workspace": str(self._workspace),
                "sandbox_notice": sandbox_notice,
            },
            native_event_type="initialize",
            native_metadata=self.model_metadata(initialized),
        )
        self._prompt_task = asyncio.create_task(self._run_prompt())

    async def _authenticate(self, methods: list[Any]) -> None:
        if not methods or self._connection is None:
            return
        supported = [method for method in methods if not isinstance(method, AuthMethodTerminal)]
        if not supported:
            raise RuntimeError(
                "This ACP agent requires terminal authentication. Run its login command in a terminal, "
                "then refresh SwiftAgent."
            )
        selected = supported[0]
        if len(supported) > 1:
            request_id = f"acp-auth-{self.task.id}"
            choices = ", ".join(f"{method.id}: {method.name}" for method in supported)
            await self.emit_event(
                AgentEventType.QUESTION_REQUESTED,
                {"request_id": request_id, "question": f"Choose an authentication method: {choices}"},
                native_event_type="initialize.authMethods",
            )
            answer = await self.manager.request_question(
                request_id,
                WSEvent(
                    type=WSEventType.QUESTION_REQUEST,
                    task_id=self.task.id,
                    payload={
                        "id": request_id,
                        "question": f"Choose an authentication method ID: {choices}",
                        "description": "SwiftAgent never asks for or stores the provider credential.",
                    },
                ),
            )
            selected = next(
                (method for method in supported if method.id == answer.strip()),
                None,
            )
            await self.emit_event(
                AgentEventType.QUESTION_RESOLVED,
                {
                    "request_id": request_id,
                    "answered": bool(answer.strip()) and selected is not None,
                },
                native_event_type="initialize.authMethods",
            )
            if selected is None:
                raise RuntimeError("No valid ACP authentication method was selected")
        await asyncio.wait_for(self._connection.authenticate(method_id=selected.id), timeout=120)

    def _apply_capabilities(self, native: Any) -> None:
        prompt = getattr(native, "prompt_capabilities", None)
        sessions = getattr(native, "session_capabilities", None)
        load_session = bool(getattr(native, "load_session", False))
        attachments: list[str] = []
        if prompt and getattr(prompt, "image", False):
            attachments.append("image/*")
        if prompt and getattr(prompt, "audio", False):
            attachments.append("audio/*")
        if prompt and getattr(prompt, "embedded_context", False):
            attachments.append("application/octet-stream")

        self.task.capability_snapshot.update(
            {
                "structured_streaming": True,
                "session_resume": load_session or bool(getattr(sessions, "resume", None)),
                "session_fork": False,
                "native_session_fork": bool(getattr(sessions, "fork", None)),
                "tool_events": True,
                "approvals": True,
                "questions": False,
                "plan_updates": True,
                # Preserve native negotiation for the future attachment router,
                # but do not advertise an input path the adapter does not yet send.
                "attachments": False,
                "attachment_types": [],
                "native_attachment_types": attachments,
                "usage": True,
                "cancellation": True,
            }
        )

    async def _apply_session_config(self, session_state: Any) -> None:
        """Discover adapter-owned options and apply a validated per-task model."""
        if self._connection is None or self._session_id is None:
            return
        raw_state = self.model_metadata(session_state)
        config_options = raw_state.get("configOptions") or []
        if not isinstance(config_options, list):
            return

        model_option = next(
            (
                option
                for option in config_options
                if isinstance(option, dict)
                and (option.get("category") == "model" or option.get("id") == "model")
            ),
            None,
        )
        self.task.capability_snapshot["mode_discovery"] = any(
            isinstance(option, dict) and option.get("category") == "mode"
            for option in config_options
        )
        if model_option is None:
            return

        choices = model_option.get("options") or []
        available_models = [
            str(choice.get("value"))
            for choice in choices
            if isinstance(choice, dict) and isinstance(choice.get("value"), str)
        ][:256]
        self.task.capability_snapshot["model_discovery"] = bool(available_models)
        self.task.capability_snapshot["available_models"] = available_models
        current_model = model_option.get("currentValue")
        if isinstance(current_model, str):
            self.task.capability_snapshot["effective_model"] = current_model

        requested_model = self.task.config.model_id
        if not requested_model:
            return
        if requested_model not in available_models:
            raise RuntimeError(
                f"The requested model is not advertised by this ACP agent: {requested_model}"
            )
        config_id = model_option.get("id")
        if not isinstance(config_id, str) or not config_id:
            raise RuntimeError("The ACP agent advertised models without a configurable option ID")
        await asyncio.wait_for(
            self._connection.set_config_option(
                config_id=config_id,
                session_id=self._session_id,
                value=requested_model,
            ),
            timeout=15,
        )
        self.task.capability_snapshot["effective_model"] = requested_model

    async def _run_prompt(self) -> None:
        assert self._connection is not None and self._session_id is not None
        try:
            response = await self._connection.prompt(
                session_id=self._session_id,
                prompt=[text_block(self.task.config.prompt)],
            )
            await self._flush_messages()
            stop_reason = response.stop_reason
            if stop_reason == "end_turn":
                await self._finish(TaskStatus.COMPLETED, success=True, summary=self._summary())
            elif stop_reason == "cancelled":
                await self._finish(
                    TaskStatus.CANCELLED,
                    success=False,
                    error="ACP turn cancelled",
                    summary=self._summary(),
                )
            else:
                await self._finish(
                    TaskStatus.FAILED,
                    success=False,
                    error=f"ACP turn stopped: {stop_reason}",
                    summary=self._summary(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._finish(TaskStatus.FAILED, success=False, error=f"ACP error: {exc}")

    async def handle_session_update(self, update: Any) -> None:
        raw = self.model_metadata(update)
        update_type = raw.get("sessionUpdate")
        if update_type in {"agent_message_chunk", "agent_thought_chunk"}:
            content = raw.get("content") or {}
            if content.get("type") != "text":
                return
            text = str(content.get("text") or "")
            if not text:
                return
            message_id = str(raw.get("messageId") or update_type)
            is_reasoning = update_type == "agent_thought_chunk"
            if not is_reasoning:
                if message_id not in self._message_chunks:
                    self._message_chunks[message_id] = []
                    self._message_order.append(message_id)
                self._message_chunks[message_id].append(text)
            await self.emit_event(
                AgentEventType.MESSAGE_DELTA,
                {
                    "message_id": message_id,
                    "role": "assistant",
                    "content": text,
                    "reasoning": is_reasoning,
                },
                native_event_type=f"session/update.{update_type}",
                native_metadata=raw,
            )
            return
        if update_type == "tool_call":
            payload = {
                "tool_call_id": raw.get("toolCallId"),
                "name": raw.get("title"),
                "kind": raw.get("kind"),
                "status": raw.get("status"),
                "input": raw.get("rawInput"),
            }
            await self.manager.broadcast(
                WSEvent(type=WSEventType.TOOL_USE, task_id=self.task.id, payload=payload)
            )
            await self.emit_event(
                AgentEventType.TOOL_STARTED,
                payload,
                native_event_type="session/update.tool_call",
                native_metadata=raw,
            )
            return
        if update_type == "tool_call_update":
            status = raw.get("status")
            event_type = (
                AgentEventType.TOOL_COMPLETED
                if status in {"completed", "failed"}
                else AgentEventType.TOOL_UPDATED
            )
            payload = {
                "tool_call_id": raw.get("toolCallId"),
                "name": raw.get("title"),
                "kind": raw.get("kind"),
                "status": status,
                "output": raw.get("rawOutput"),
                "content": raw.get("content"),
            }
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TOOL_RESULT,
                    task_id=self.task.id,
                    payload={**payload, "is_error": status == "failed"},
                )
            )
            await self.emit_event(
                event_type,
                payload,
                native_event_type="session/update.tool_call_update",
                native_metadata=raw,
            )
            return
        if update_type == "plan":
            await self.emit_event(
                AgentEventType.PLAN_UPDATED,
                {"entries": raw.get("entries") or []},
                native_event_type="session/update.plan",
                native_metadata=raw,
            )
            return
        if update_type == "usage_update":
            await self.emit_event(
                AgentEventType.USAGE_UPDATED,
                {"used": raw.get("used"), "size": raw.get("size"), "cost": raw.get("cost")},
                native_event_type="session/update.usage_update",
                native_metadata=raw,
            )
            return
        logger.debug("acp_unknown_update task_id=%s update=%s", self.task.id, update_type)

    async def _flush_messages(self) -> None:
        for message_id in self._message_order:
            content = "".join(self._message_chunks[message_id])
            if not content:
                continue
            message = TaskMessage(
                role="assistant",
                content=content,
                metadata={"message_id": message_id, "protocol": "acp"},
            )
            task_repo.add_task_message(self.task.id, message)
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_MESSAGE,
                    task_id=self.task.id,
                    payload={"role": "assistant", "content": content},
                )
            )
            await self.emit_event(
                AgentEventType.MESSAGE_COMPLETED,
                {"message_id": message_id, "role": "assistant", "content": content},
                native_event_type="session/prompt.flush",
            )

    def _summary(self) -> str | None:
        parts = ["".join(self._message_chunks[key]) for key in self._message_order]
        summary = "\n\n".join(part for part in parts if part).strip()
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
            await self.emit_event(
                AgentEventType.RUN_COMPLETED if status is not TaskStatus.FAILED else AgentEventType.RUN_FAILED,
                {"status": status.value, "success": success, "error": error, "summary": summary},
                native_event_type="session/prompt.result",
            )

    async def wait(self) -> None:
        if self._prompt_task:
            await self._prompt_task
        await self._close_resources()

    async def fail(self, error: str) -> None:
        await self._finish(TaskStatus.FAILED, success=False, error=error)

    async def cancel(self) -> None:
        self._cancel_event.set()
        if self._connection and self._session_id:
            with contextlib.suppress(Exception):
                await self._connection.cancel(session_id=self._session_id)
        if self._prompt_task and not self._prompt_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._prompt_task), timeout=2)
            except TimeoutError:
                self._terminate_process()
        await self._finish(
            TaskStatus.CANCELLED,
            success=False,
            error="ACP turn cancelled",
            summary=self._summary(),
        )

    async def _close_resources(self) -> None:
        if self._bridge:
            await self._bridge.close()
        if self._connection:
            await self._connection.close()
            self._connection = None
        if self._process and self._process.returncode is None:
            self._terminate_process()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except TimeoutError:
                self._kill_process()
                with contextlib.suppress(Exception):
                    await self._process.wait()
        if self._stderr_task:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stderr_task

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

    def dispose(self) -> None:
        self._disposed = True
        self._terminate_process()

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        retained = 0
        async for line in self._process.stderr:
            if retained >= 65_536:
                continue
            text = line.decode("utf-8", errors="replace").strip()
            retained += len(line)
            if text:
                logger.warning("acp_stderr task_id=%s message=%s", self.task.id, text[:2_048])

    def _observe_stream(self, event: StreamEvent) -> None:
        logger.debug(
            "acp_rpc task_id=%s direction=%s method=%s",
            self.task.id,
            event.direction.value,
            event.message.get("method"),
        )

    async def emit_event(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any],
        *,
        native_event_type: str,
        native_metadata: dict[str, Any] | None = None,
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
                native_metadata=self._bounded_metadata(native_metadata or {}),
            )
        )

    @staticmethod
    def model_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", by_alias=True, exclude_none=True)
        return value if isinstance(value, dict) else {"value": str(value)}

    @staticmethod
    def _bounded_metadata(value: dict[str, Any], max_chars: int = 16_384) -> dict[str, Any]:
        return AcpClientBridge.diagnostics(value, max_chars=max_chars)
