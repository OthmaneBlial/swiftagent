"""Codex app-server v2 adapter with native approvals and thread resumption."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from swiftagent.agents.codex import settings as codex_settings
from swiftagent.agents.codex.protocol import CodexProtocolError, CodexRpcConnection
from swiftagent.agents.codex.status import resolve_cli_path
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
MAX_NATIVE_METADATA_CHARS = 16_384
MAX_STDERR_BYTES = 65_536
TOOL_ITEM_TYPES = {
    "commandExecution",
    "fileChange",
    "mcpToolCall",
    "dynamicToolCall",
    "collabAgentToolCall",
    "webSearch",
    "imageView",
    "imageGeneration",
}


class CodexAdapter:
    """Own one local app-server process for one SwiftAgent task."""

    def __init__(
        self,
        task: Task,
        manager: ConnectionManager,
        *,
        command: list[str] | None = None,
    ):
        self.task = task
        self.manager = manager
        self._command = command
        self._process: asyncio.subprocess.Process | None = None
        self._rpc: CodexRpcConnection | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._workspace: Path | None = None
        self._session_id = task.native_session_id or task.session_id
        self._turn_id: str | None = None
        self._turn_done = asyncio.Event()
        self._cancel_event = asyncio.Event()
        self._completion_lock = asyncio.Lock()
        self._completed = False
        self._disposed = False
        self._last_error: str | None = None
        self._messages: dict[str, str] = {}
        self._message_phases: dict[str, str | None] = {}
        self._message_order: list[str] = []

    @property
    def running(self) -> bool:
        return bool(
            self._process
            and self._process.returncode is None
            and not self._completed
            and not self._disposed
        )

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def start(self) -> None:
        if self._disposed:
            raise RuntimeError("Adapter disposed")
        configured = self._command
        if configured is None:
            executable = resolve_cli_path()
            if not executable:
                raise RuntimeError("Codex CLI not found. Install Codex or configure its path.")
            configured = [executable, "app-server", "--listen", "stdio://"]

        self._workspace = (
            Path(self.task.config.working_directory).resolve()
            if self.task.config.working_directory
            else get_workspace_dir()
        )
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()
        writable_paths = ()
        if codex_home != self._workspace and self._workspace not in codex_home.parents:
            writable_paths = (codex_home,)
        command, sandbox_notice = wrap_command_for_sandbox(
            configured,
            self._workspace,
            settings_repo.get_sandbox_mode(),
            writable_paths=writable_paths,
        )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._workspace),
            env=os.environ.copy(),
            start_new_session=True,
            limit=2 * 1024 * 1024,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("Codex app-server did not expose stdio")
        self._stderr_task = asyncio.create_task(self._read_stderr())
        self._rpc = CodexRpcConnection(
            self._process.stdout,
            self._process.stdin,
            on_notification=self._on_notification,
            on_request=self._on_server_request,
            on_disconnect=self._on_disconnect,
        )
        self._rpc.start()

        initialized = await self._rpc.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "swiftagent",
                    "title": "SwiftAgent",
                    "version": "0.4.0-dev",
                },
                "capabilities": {"experimentalApi": False},
            },
            timeout=15,
        )
        await self._rpc.notify("initialized")
        account = await self._rpc.request(
            "account/read", {"refreshToken": False}, timeout=15
        )
        if account.get("requiresOpenaiAuth") and not account.get("account"):
            raise RuntimeError(
                "Codex authentication is required. Run `codex login` in a terminal, then refresh SwiftAgent."
            )

        models: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            model_result = await self._rpc.request(
                "model/list", {"limit": 100, "includeHidden": False}, timeout=15
            )
            raw_models = model_result.get("data")
            if isinstance(raw_models, list):
                models = [row for row in raw_models if isinstance(row, dict)][:100]

        thread_params = self._thread_params()
        if self._session_id:
            thread_params["threadId"] = self._session_id
            thread_result = await self._rpc.request("thread/resume", thread_params, timeout=30)
        else:
            thread_result = await self._rpc.request("thread/start", thread_params, timeout=30)
        thread = thread_result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise CodexProtocolError("Codex thread response did not include a thread id")
        self._session_id = thread["id"]
        self.task.native_session_id = self._session_id
        self.task.session_id = self._session_id
        self.task.capability_snapshot.update(
            {
                "structured_streaming": True,
                "session_resume": True,
                "session_fork": False,
                "native_session_fork": True,
                "tool_events": True,
                "approvals": True,
                "questions": True,
                "plan_updates": True,
                "attachments": True,
                "attachment_types": ["image/*"],
                "model_discovery": bool(models),
                "available_models": [
                    {
                        "id": row.get("id") or row.get("model"),
                        "model": row.get("model"),
                        "display_name": row.get("displayName"),
                        "is_default": bool(row.get("isDefault")),
                    }
                    for row in models
                    if isinstance(row.get("id") or row.get("model"), str)
                ],
                "usage": True,
                "native_sandbox": True,
                "native_sandbox_mode": codex_settings.get_sandbox_mode(),
                "native_approval_policy": codex_settings.get_approval_policy(),
                "cancellation": True,
            }
        )
        task_repo.update_task_native_session_id(self.task.id, self._session_id)
        task_repo.update_task_capability_snapshot(self.task.id, self.task.capability_snapshot)

        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TASK_PROGRESS,
                task_id=self.task.id,
                payload={
                    "stage": "starting",
                    "message": "Codex app-server thread is ready",
                    "workspace": str(self._workspace),
                    "sandbox_notice": sandbox_notice,
                },
            )
        )
        await self._emit_event(
            AgentEventType.RUN_STARTED,
            {
                "workspace": str(self._workspace),
                "sandbox_notice": sandbox_notice,
                "platform_family": initialized.get("platformFamily"),
                "platform_os": initialized.get("platformOs"),
            },
            native_event_type="initialize",
            native_metadata=initialized,
        )

        turn_result = await self._rpc.request(
            "turn/start", self._turn_params(), timeout=30
        )
        turn = turn_result.get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
            raise CodexProtocolError("Codex turn response did not include a turn id")
        self._turn_id = turn["id"]

    def _thread_params(self) -> dict[str, Any]:
        assert self._workspace is not None
        policy = codex_settings.get_approval_policy()
        sandbox = codex_settings.get_sandbox_mode()
        codex_settings.validate_safety_combination(
            policy,
            sandbox,
            codex_settings.get_allow_dangerous_bypass(),
        )
        params: dict[str, Any] = {
            "cwd": str(self._workspace),
            "approvalPolicy": policy,
            "approvalsReviewer": "user",
            "sandbox": sandbox,
        }
        model = self.task.config.model_id or codex_settings.get_model()
        if model:
            params["model"] = model
        return params

    def _turn_params(self) -> dict[str, Any]:
        assert self._workspace is not None and self._session_id is not None
        sandbox = codex_settings.get_sandbox_mode()
        if sandbox == "read-only":
            sandbox_policy: dict[str, Any] = {"type": "readOnly", "networkAccess": False}
        elif sandbox == "danger-full-access":
            sandbox_policy = {"type": "dangerFullAccess"}
        else:
            sandbox_policy = {
                "type": "workspaceWrite",
                "writableRoots": [],
                "networkAccess": False,
            }
        inputs: list[dict[str, Any]] = [{"type": "text", "text": self.task.config.prompt}]
        for attachment in self.task.config.attachments:
            path = Path(attachment.path).expanduser().resolve(strict=False)
            if path != self._workspace and self._workspace not in path.parents:
                raise ValueError("Codex attachment path must stay inside the selected workspace")
            if not path.is_file():
                raise ValueError(f"Codex attachment does not exist: {attachment.name}")
            if not (attachment.mime_type or "").startswith("image/"):
                raise ValueError("This Codex adapter currently supports image attachments only")
            inputs.append({"type": "localImage", "path": str(path)})

        params: dict[str, Any] = {
            "threadId": self._session_id,
            "input": inputs,
            "cwd": str(self._workspace),
            "approvalPolicy": codex_settings.get_approval_policy(),
            "approvalsReviewer": "user",
            "sandboxPolicy": sandbox_policy,
        }
        model = self.task.config.model_id or codex_settings.get_model()
        if model:
            params["model"] = model
        return params

    async def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        if self._completed:
            return
        thread_id = params.get("threadId")
        if thread_id is not None and self._session_id and thread_id != self._session_id:
            logger.debug("codex_ignored_foreign_thread task_id=%s method=%s", self.task.id, method)
            return
        if method == "turn/started":
            turn = params.get("turn") or {}
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                self._turn_id = turn["id"]
            return
        if method == "item/agentMessage/delta":
            item_id = str(params.get("itemId") or "agent-message")
            delta = str(params.get("delta") or "")
            if delta:
                self._append_message(item_id, delta)
                await self._emit_event(
                    AgentEventType.MESSAGE_DELTA,
                    {"message_id": item_id, "role": "assistant", "content": delta},
                    native_event_type=method,
                    native_metadata=params,
                )
            return
        if method in {
            "item/reasoning/textDelta",
            "item/reasoning/summaryTextDelta",
            "item/reasoning/summaryPartAdded",
        }:
            delta = str(params.get("delta") or params.get("text") or "")
            if delta:
                await self._emit_event(
                    AgentEventType.MESSAGE_DELTA,
                    {
                        "message_id": str(params.get("itemId") or "reasoning"),
                        "role": "assistant",
                        "content": delta,
                        "reasoning": True,
                    },
                    native_event_type=method,
                    native_metadata=params,
                )
            return
        if method == "item/started":
            await self._handle_item(params.get("item"), completed=False, method=method)
            return
        if method == "item/completed":
            await self._handle_item(params.get("item"), completed=True, method=method)
            return
        if method in {
            "item/commandExecution/outputDelta",
            "item/fileChange/outputDelta",
            "turn/diff/updated",
        }:
            await self._emit_event(
                AgentEventType.TOOL_UPDATED,
                {
                    "tool_call_id": params.get("itemId") or self._turn_id,
                    "content": params.get("delta") or params.get("diff"),
                },
                native_event_type=method,
                native_metadata=params,
            )
            return
        if method == "turn/plan/updated":
            await self._emit_event(
                AgentEventType.PLAN_UPDATED,
                {"entries": params.get("plan") or [], "explanation": params.get("explanation")},
                native_event_type=method,
                native_metadata=params,
            )
            return
        if method == "thread/tokenUsage/updated":
            await self._emit_event(
                AgentEventType.USAGE_UPDATED,
                {"token_usage": params.get("tokenUsage") or {}},
                native_event_type=method,
                native_metadata=params,
            )
            return
        if method == "error":
            error = params.get("error") or {}
            self._last_error = (
                str(error.get("message") or "Codex turn failed")
                if isinstance(error, dict)
                else str(error)
            )
            return
        if method in {"warning", "configWarning"}:
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_PROGRESS,
                    task_id=self.task.id,
                    payload={"stage": "warning", "message": params.get("message") or params.get("summary")},
                )
            )
            return
        if method == "turn/completed":
            turn = params.get("turn") or {}
            status = turn.get("status") if isinstance(turn, dict) else None
            error = turn.get("error") if isinstance(turn, dict) else None
            if isinstance(error, dict) and error.get("message"):
                self._last_error = str(error["message"])
            await self._flush_messages()
            if self._cancel_event.is_set():
                await self._finish(
                    TaskStatus.CANCELLED,
                    success=False,
                    error="Codex turn interrupted",
                    summary=self._summary(),
                )
            elif status == "completed":
                await self._finish(TaskStatus.COMPLETED, success=True, summary=self._summary())
            elif status == "interrupted":
                await self._finish(
                    TaskStatus.CANCELLED,
                    success=False,
                    error="Codex turn interrupted",
                    summary=self._summary(),
                )
            else:
                await self._finish(
                    TaskStatus.FAILED,
                    success=False,
                    error=self._last_error or f"Codex turn ended with status: {status}",
                    summary=self._summary(),
                )
            return
        logger.debug("codex_unknown_notification task_id=%s method=%s", self.task.id, method)

    def _append_message(self, item_id: str, delta: str) -> None:
        if item_id not in self._messages:
            self._messages[item_id] = ""
            self._message_order.append(item_id)
        self._messages[item_id] += delta

    async def _handle_item(self, raw_item: Any, *, completed: bool, method: str) -> None:
        if not isinstance(raw_item, dict):
            return
        item_type = raw_item.get("type")
        item_id = str(raw_item.get("id") or item_type or "item")
        if item_type == "agentMessage" and completed:
            text = str(raw_item.get("text") or "")
            if item_id not in self._messages:
                self._message_order.append(item_id)
            self._messages[item_id] = text
            self._message_phases[item_id] = raw_item.get("phase")
            return
        if item_type == "plan" and completed:
            await self._emit_event(
                AgentEventType.PLAN_UPDATED,
                {"text": raw_item.get("text")},
                native_event_type=method,
                native_metadata=raw_item,
            )
            return
        if item_type not in TOOL_ITEM_TYPES:
            return
        payload = {
            "tool_call_id": item_id,
            "name": self._tool_name(raw_item),
            "kind": item_type,
            "status": raw_item.get("status"),
            "input": self._tool_input(raw_item),
            "output": self._tool_output(raw_item) if completed else None,
        }
        event_type = AgentEventType.TOOL_COMPLETED if completed else AgentEventType.TOOL_STARTED
        await self.manager.broadcast(
            WSEvent(
                type=WSEventType.TOOL_RESULT if completed else WSEventType.TOOL_USE,
                task_id=self.task.id,
                payload={**payload, "is_error": raw_item.get("status") == "failed"},
            )
        )
        await self._emit_event(
            event_type,
            payload,
            native_event_type=method,
            native_metadata=raw_item,
        )

    @staticmethod
    def _tool_name(item: dict[str, Any]) -> str:
        item_type = item.get("type")
        if item_type == "commandExecution":
            return str(item.get("command") or "Command")
        if item_type == "fileChange":
            return "Apply file changes"
        if item_type == "mcpToolCall":
            return f"{item.get('server')}/{item.get('tool')}"
        if item_type == "dynamicToolCall":
            namespace = f"{item.get('namespace')}/" if item.get("namespace") else ""
            return f"{namespace}{item.get('tool')}"
        if item_type == "webSearch":
            return "Web search"
        return str(item_type or "Codex tool")

    @staticmethod
    def _tool_input(item: dict[str, Any]) -> Any:
        for key in ("arguments", "changes", "query", "path", "command"):
            if key in item:
                return item[key]
        return None

    @staticmethod
    def _tool_output(item: dict[str, Any]) -> Any:
        for key in ("aggregatedOutput", "result", "contentItems", "exitCode", "failure"):
            if item.get(key) is not None:
                return item[key]
        return None

    async def _on_server_request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            return await self._handle_approval(method, params)
        if method == "item/tool/requestUserInput":
            return await self._handle_questions(params)
        raise CodexProtocolError(f"Unsupported Codex server request: {method}")

    async def _handle_approval(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if params.get("threadId") != self._session_id:
            raise CodexProtocolError("Approval belongs to an unknown Codex thread")
        request_id = "codex-" + str(params.get("approvalId") or params.get("itemId") or uuid.uuid4().hex)
        title = {
            "item/commandExecution/requestApproval": "Codex command approval",
            "item/fileChange/requestApproval": "Codex file-change approval",
            "item/permissions/requestApproval": "Codex permission request",
        }[method]
        detail = params.get("reason") or params.get("command") or title
        await self._emit_event(
            AgentEventType.APPROVAL_REQUESTED,
            {"request_id": request_id, "tool_call_id": params.get("itemId"), "title": title},
            native_event_type=method,
            native_metadata=params,
        )
        approval_task = asyncio.create_task(
            self.manager.request_permission(
                request_id,
                WSEvent(
                    type=WSEventType.PERMISSION_REQUEST,
                    task_id=self.task.id,
                    payload={
                        "id": request_id,
                        "tool_name": title,
                        "description": str(detail)[:4_096],
                        "metadata": self._bounded_metadata(params),
                    },
                ),
            )
        )
        cancel_task = asyncio.create_task(self._cancel_event.wait())
        done, pending = await asyncio.wait(
            {approval_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        approved = approval_task in done and bool(approval_task.result())
        await self._emit_event(
            AgentEventType.APPROVAL_RESOLVED,
            {"request_id": request_id, "outcome": "accept" if approved else "decline"},
            native_event_type=method,
        )
        if method == "item/permissions/requestApproval":
            requested = params.get("permissions") if approved else {}
            return {"permissions": requested if isinstance(requested, dict) else {}, "scope": "turn"}
        return {"decision": "accept" if approved else "decline"}

    async def _handle_questions(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("threadId") != self._session_id:
            raise CodexProtocolError("Question belongs to an unknown Codex thread")
        answers: dict[str, dict[str, list[str]]] = {}
        for question in (params.get("questions") or [])[:3]:
            if not isinstance(question, dict) or not isinstance(question.get("id"), str):
                continue
            question_id = question["id"]
            if question.get("isSecret"):
                answers[question_id] = {"answers": []}
                continue
            options = question.get("options") or []
            option_text = ", ".join(
                str(option.get("label") or option.get("description") or "")
                for option in options
                if isinstance(option, dict)
            )
            prompt = str(question.get("question") or "Codex needs input")
            if option_text:
                prompt = f"{prompt} Choices: {option_text}"
            request_id = f"codex-question-{self.task.id}-{question_id}"
            await self._emit_event(
                AgentEventType.QUESTION_REQUESTED,
                {"request_id": request_id, "question": prompt},
                native_event_type="item/tool/requestUserInput",
                native_metadata=question,
            )
            answer = await self.manager.request_question(
                request_id,
                WSEvent(
                    type=WSEventType.QUESTION_REQUEST,
                    task_id=self.task.id,
                    payload={"id": request_id, "question": prompt},
                ),
            )
            await self._emit_event(
                AgentEventType.QUESTION_RESOLVED,
                {"request_id": request_id, "answered": bool(answer)},
                native_event_type="item/tool/requestUserInput",
            )
            answers[question_id] = {"answers": [answer] if answer else []}
        return {"answers": answers}

    async def _on_disconnect(self, reason: str) -> None:
        if self._completed or self._disposed:
            return
        await self._finish(
            TaskStatus.FAILED,
            success=False,
            error=f"Codex app-server connection ended: {reason}",
            summary=self._summary(),
        )

    async def _flush_messages(self) -> None:
        for item_id in self._message_order:
            content = self._messages.get(item_id, "").strip()
            if not content:
                continue
            phase = self._message_phases.get(item_id)
            message = TaskMessage(
                role="assistant",
                content=content,
                metadata={"item_id": item_id, "protocol": "codex-app-server-v2", "phase": phase},
            )
            task_repo.add_task_message(self.task.id, message)
            await self.manager.broadcast(
                WSEvent(
                    type=WSEventType.TASK_MESSAGE,
                    task_id=self.task.id,
                    payload={"role": "assistant", "content": content},
                )
            )
            await self._emit_event(
                AgentEventType.MESSAGE_COMPLETED,
                {"message_id": item_id, "role": "assistant", "content": content, "phase": phase},
                native_event_type="item/completed",
            )

    def _summary(self) -> str | None:
        final = [
            self._messages[item_id]
            for item_id in self._message_order
            if self._message_phases.get(item_id) == "final_answer" and self._messages.get(item_id)
        ]
        parts = final or [self._messages[item_id] for item_id in self._message_order if self._messages.get(item_id)]
        summary = "\n\n".join(parts).strip()
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
            await self._emit_event(
                AgentEventType.RUN_FAILED if status is TaskStatus.FAILED else AgentEventType.RUN_COMPLETED,
                {"status": status.value, "success": success, "error": error, "summary": summary},
                native_event_type="turn/completed",
            )
            self._turn_done.set()

    async def wait(self) -> None:
        await self._turn_done.wait()
        await self._close_resources()

    async def fail(self, error: str) -> None:
        await self._finish(TaskStatus.FAILED, success=False, error=error, summary=self._summary())
        await self._close_resources()

    async def cancel(self) -> None:
        self._cancel_event.set()
        if self._rpc and self._session_id and self._turn_id and not self._completed:
            with contextlib.suppress(Exception):
                await self._rpc.request(
                    "turn/interrupt",
                    {"threadId": self._session_id, "turnId": self._turn_id},
                    timeout=5,
                )
            try:
                await asyncio.wait_for(self._turn_done.wait(), timeout=2)
            except TimeoutError:
                self._terminate_process()
        await self._finish(
            TaskStatus.CANCELLED,
            success=False,
            error="Codex turn interrupted",
            summary=self._summary(),
        )
        await self._close_resources()

    async def _close_resources(self) -> None:
        if self._rpc:
            await self._rpc.close()
            self._rpc = None
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
            if retained >= MAX_STDERR_BYTES:
                continue
            retained += len(line)
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.warning("codex_stderr task_id=%s message=%s", self.task.id, text[:2_048])

    async def _emit_event(
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
    def _bounded_metadata(value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = str(value)
        if len(encoded) <= MAX_NATIVE_METADATA_CHARS:
            return value
        return {
            "truncated": True,
            "original_chars": len(encoded),
            "preview": encoded[:MAX_NATIVE_METADATA_CHARS],
        }
