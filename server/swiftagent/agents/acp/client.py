"""SwiftAgent's workspace-contained implementation of ACP client callbacks."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from acp import RequestError, default_environment
from acp.schema import (
    AllowedOutcome,
    CreateTerminalResponse,
    DeclineElicitationResponse,
    DeniedOutcome,
    EnvVariable,
    KillTerminalResponse,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    TerminalExitStatus,
    TerminalOutputResponse,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

from swiftagent.models.agent import AgentEventType
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.storage import settings as settings_repo
from swiftagent.tools.sandbox import wrap_command_for_sandbox
from swiftagent.tools.workspace import write_text_atomically

if TYPE_CHECKING:
    from swiftagent.agents.acp.adapter import AcpAdapter


MAX_FILE_BYTES = 1_048_576
MAX_FILE_LINES = 10_000
MAX_TERMINALS = 8
MAX_TERMINAL_OUTPUT_BYTES = 1_048_576
MAX_TERMINAL_ARGS = 256
MAX_TERMINAL_ENV = 64
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


@dataclass
class _Terminal:
    process: asyncio.subprocess.Process
    output_limit: int
    output: bytes = b""
    truncated: bool = False
    reader_task: asyncio.Task[None] | None = field(default=None)

    def append(self, chunk: bytes) -> None:
        combined = self.output + chunk
        if len(combined) <= self.output_limit:
            self.output = combined
            return
        self.truncated = True
        if self.output_limit == 0:
            self.output = b""
            return
        self.output = combined[-self.output_limit :]

    def text(self) -> str:
        return self.output.decode("utf-8", errors="ignore")


class AcpClientBridge:
    """Methods an ACP agent may call on the SwiftAgent client."""

    def __init__(self, adapter: AcpAdapter, workspace: Path):
        self.adapter = adapter
        self.workspace = workspace.resolve()
        self._terminals: dict[str, _Terminal] = {}

    def on_connect(self, _agent: Any) -> None:
        return None

    def _check_session(self, session_id: str) -> None:
        expected = self.adapter.session_id
        if not expected or session_id != expected:
            raise RequestError.invalid_params({"details": "Unknown or inactive ACP session"})

    def _resolve_absolute(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise RequestError.invalid_params({"details": "ACP paths must be absolute"})
        resolved = path.resolve(strict=False)
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise RequestError.invalid_params(
                {"details": f"Path escapes selected workspace: {raw_path}"}
            )
        return resolved

    async def request_permission(
        self,
        session_id: str,
        tool_call: Any,
        options: list[Any],
        **_kwargs: Any,
    ) -> RequestPermissionResponse:
        self._check_session(session_id)
        request_id = f"acp-{uuid.uuid4().hex[:16]}"
        option_rows = [
            {
                "id": option.option_id,
                "name": option.name,
                "kind": option.kind,
            }
            for option in options
        ]
        title = getattr(tool_call, "title", None) or "ACP tool request"
        await self.adapter.emit_event(
            AgentEventType.APPROVAL_REQUESTED,
            {"request_id": request_id, "tool_call_id": tool_call.tool_call_id, "options": option_rows},
            native_event_type="session/request_permission",
            native_metadata={"toolCall": self.adapter.model_metadata(tool_call)},
        )
        approval_task = asyncio.create_task(
            self.adapter.manager.request_permission(
                request_id,
                WSEvent(
                    type=WSEventType.PERMISSION_REQUEST,
                    task_id=self.adapter.task.id,
                    payload={
                        "id": request_id,
                        "tool_name": title,
                        "description": (
                            f"{title}\n\nNative choices: "
                            + ", ".join(f"{row['name']} ({row['kind']})" for row in option_rows)
                        ),
                        "metadata": {"options": option_rows},
                    },
                ),
            )
        )
        cancel_task = asyncio.create_task(self.adapter.cancel_event.wait())
        done, pending = await asyncio.wait(
            {approval_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if cancel_task in done and cancel_task.result():
            await self.adapter.emit_event(
                AgentEventType.APPROVAL_RESOLVED,
                {"request_id": request_id, "outcome": "cancelled"},
                native_event_type="session/request_permission",
            )
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

        approved = approval_task.result()
        preferred_kinds = {"allow_once", "allow_always"} if approved else {
            "reject_once",
            "reject_always",
        }
        selected = next((option for option in options if option.kind in preferred_kinds), None)
        if selected is None:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        await self.adapter.emit_event(
            AgentEventType.APPROVAL_RESOLVED,
            {"request_id": request_id, "outcome": "selected", "option_id": selected.option_id},
            native_event_type="session/request_permission",
        )
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="selected", optionId=selected.option_id)
        )

    async def session_update(self, session_id: str, update: Any, **_kwargs: Any) -> None:
        self._check_session(session_id)
        await self.adapter.handle_session_update(update)

    async def read_text_file(
        self,
        session_id: str,
        path: str,
        line: int | None = None,
        limit: int | None = None,
        **_kwargs: Any,
    ) -> ReadTextFileResponse:
        self._check_session(session_id)
        target = self._resolve_absolute(path)
        if not target.is_file():
            raise RequestError.invalid_params({"details": "Requested path is not a file"})
        if target.stat().st_size > MAX_FILE_BYTES:
            raise RequestError.invalid_params({"details": "Requested file exceeds 1 MiB"})
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RequestError.invalid_params({"details": "Requested file is not UTF-8 text"}) from exc

        if line is not None and line < 1:
            raise RequestError.invalid_params({"details": "ACP line numbers are 1-based"})
        if limit is not None and (limit < 0 or limit > MAX_FILE_LINES):
            raise RequestError.invalid_params(
                {"details": f"Read limit must be between 0 and {MAX_FILE_LINES} lines"}
            )
        if line is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            start = (line or 1) - 1
            content = "".join(lines[start : start + limit if limit is not None else None])
        return ReadTextFileResponse(content=content)

    async def write_text_file(
        self,
        session_id: str,
        path: str,
        content: str,
        **_kwargs: Any,
    ) -> WriteTextFileResponse:
        self._check_session(session_id)
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise RequestError.invalid_params({"details": "File content exceeds 1 MiB"})
        target = self._resolve_absolute(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomically(target, content)
        return WriteTextFileResponse()

    async def create_terminal(
        self,
        session_id: str,
        command: str,
        args: list[str] | None = None,
        env: list[EnvVariable] | None = None,
        cwd: str | None = None,
        output_byte_limit: int | None = None,
        **_kwargs: Any,
    ) -> CreateTerminalResponse:
        self._check_session(session_id)
        if len(self._terminals) >= MAX_TERMINALS:
            raise RequestError.invalid_params({"details": "Too many active ACP terminals"})
        if not command or len(command) > 4_096:
            raise RequestError.invalid_params({"details": "Terminal command is empty or too long"})
        literal_args = args or []
        if len(literal_args) > MAX_TERMINAL_ARGS or any(len(arg) > 16_384 for arg in literal_args):
            raise RequestError.invalid_params({"details": "Terminal argument limits exceeded"})
        terminal_cwd = self._resolve_absolute(cwd) if cwd else self.workspace
        if not terminal_cwd.is_dir():
            raise RequestError.invalid_params({"details": "Terminal cwd is not a directory"})

        process_env = default_environment()
        env_rows = env or []
        if len(env_rows) > MAX_TERMINAL_ENV:
            raise RequestError.invalid_params({"details": "Too many terminal environment variables"})
        for item in env_rows:
            if not _ENV_NAME.fullmatch(item.name) or len(item.value) > 16_384:
                raise RequestError.invalid_params({"details": "Invalid terminal environment variable"})
            process_env[item.name] = item.value

        requested_limit = (
            65_536 if output_byte_limit is None else max(0, int(output_byte_limit))
        )
        retained_limit = min(requested_limit, MAX_TERMINAL_OUTPUT_BYTES)
        argv, _notice = wrap_command_for_sandbox(
            [command, *literal_args],
            self.workspace,
            settings_repo.get_sandbox_mode(),
        )
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(terminal_cwd),
            env=process_env,
            start_new_session=True,
        )
        terminal_id = uuid.uuid4().hex[:16]
        terminal = _Terminal(process=process, output_limit=retained_limit)
        terminal.reader_task = asyncio.create_task(self._capture_terminal_output(terminal))
        self._terminals[terminal_id] = terminal
        return CreateTerminalResponse(terminalId=terminal_id)

    async def _capture_terminal_output(self, terminal: _Terminal) -> None:
        if terminal.process.stdout is None:
            return
        async for chunk in terminal.process.stdout:
            terminal.append(chunk)

    def _terminal(self, terminal_id: str) -> _Terminal:
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise RequestError.invalid_params({"details": "Unknown ACP terminal"})
        return terminal

    @staticmethod
    def _exit_status(process: asyncio.subprocess.Process) -> TerminalExitStatus | None:
        returncode = process.returncode
        if returncode is None:
            return None
        if returncode < 0:
            try:
                name = signal.Signals(-returncode).name
            except ValueError:
                name = f"SIG{-returncode}"
            return TerminalExitStatus(exitCode=None, signal=name)
        return TerminalExitStatus(exitCode=returncode, signal=None)

    async def terminal_output(
        self, session_id: str, terminal_id: str, **_kwargs: Any
    ) -> TerminalOutputResponse:
        self._check_session(session_id)
        terminal = self._terminal(terminal_id)
        return TerminalOutputResponse(
            output=terminal.text(),
            truncated=terminal.truncated,
            exitStatus=self._exit_status(terminal.process),
        )

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **_kwargs: Any
    ) -> WaitForTerminalExitResponse:
        self._check_session(session_id)
        terminal = self._terminal(terminal_id)
        await terminal.process.wait()
        if terminal.reader_task:
            await terminal.reader_task
        status = self._exit_status(terminal.process)
        return WaitForTerminalExitResponse(
            exitCode=status.exit_code if status else None,
            signal=status.signal if status else None,
        )

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **_kwargs: Any
    ) -> KillTerminalResponse:
        self._check_session(session_id)
        terminal = self._terminal(terminal_id)
        if terminal.process.returncode is None:
            try:
                os.killpg(terminal.process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                terminal.process.terminate()
        return KillTerminalResponse()

    async def release_terminal(
        self, session_id: str, terminal_id: str, **_kwargs: Any
    ) -> ReleaseTerminalResponse:
        self._check_session(session_id)
        terminal = self._terminal(terminal_id)
        if terminal.process.returncode is None:
            await self.kill_terminal(session_id, terminal_id)
            try:
                await asyncio.wait_for(terminal.process.wait(), timeout=2)
            except TimeoutError:
                terminal.process.kill()
                await terminal.process.wait()
        if terminal.reader_task:
            await terminal.reader_task
        self._terminals.pop(terminal_id, None)
        return ReleaseTerminalResponse()

    async def create_elicitation(
        self, _message: str, _mode: Any, **_kwargs: Any
    ) -> DeclineElicitationResponse:
        # SwiftAgent does not advertise elicitation until its schema-driven form UI ships.
        return DeclineElicitationResponse(action="decline")

    async def complete_elicitation(self, _elicitation_id: str, **_kwargs: Any) -> None:
        return None

    async def ext_method(self, method: str, _params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(f"_{method}")

    async def ext_notification(self, _method: str, _params: dict[str, Any]) -> None:
        return None

    async def close(self) -> None:
        for terminal_id in list(self._terminals):
            try:
                await self.release_terminal(self.adapter.session_id or "", terminal_id)
            except Exception:
                terminal = self._terminals.pop(terminal_id, None)
                if terminal and terminal.process.returncode is None:
                    terminal.process.kill()

    @staticmethod
    def diagnostics(value: Any, max_chars: int = 16_384) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = str(value)
        if len(encoded) <= max_chars:
            return value if isinstance(value, dict) else {"value": value}
        return {"truncated": True, "original_chars": len(encoded), "preview": encoded[:max_chars]}
