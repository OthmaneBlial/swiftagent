"""
OpenCode adapter — spawns the opencode CLI and manages its lifecycle.

Ported from base/accomplish/packages/agent-core/src/internal/classes/OpenCodeAdapter.ts
Uses asyncio.create_subprocess_exec instead of node-pty.

SAFETY: All tasks run inside a sandboxed workspace (~/.swiftagent/workspace)
so the agent cannot modify files outside that directory.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from swiftagent.engine.parser import MessageType, ParsedMessage, StreamParser
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import Task, TaskConfig, TaskMessage, TaskResult, TaskStatus
from swiftagent.storage import tasks as task_repo

if TYPE_CHECKING:
    from swiftagent.api.websocket import ConnectionManager


def _get_workspace_dir() -> Path:
    """Get the sandboxed workspace directory.

    All agent tasks execute inside ~/.swiftagent/workspace.
    The agent can create/delete files here but cannot touch
    anything outside this directory.
    """
    base = os.environ.get("SWIFTAGENT_DATA_DIR")
    if base:
        workspace = Path(base) / "workspace"
    else:
        workspace = Path.home() / ".swiftagent" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


class OpenCodeAdapter:
    """
    Manages an opencode CLI subprocess for a single task.

    Spawns the CLI with `opencode run "prompt"`, parses its output
    stream, and emits typed events to the WebSocket ConnectionManager.

    SAFETY: The subprocess CWD is always the sandboxed workspace.
    """

    def __init__(self, task: Task, manager: ConnectionManager):
        self.task = task
        self.manager = manager
        self._process: asyncio.subprocess.Process | None = None
        self._disposed = False
        self._session_id: str | None = None
        self._parser = StreamParser(self._handle_message)

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def start(self) -> None:
        """Start the opencode CLI subprocess inside the sandbox."""
        cli = self._find_cli()
        if not cli:
            raise RuntimeError("OpenCode CLI not found. Install it with: npm i -g opencode-ai")

        env = self._build_env()
        args = self._build_args()
        workspace = _get_workspace_dir()

        # Emit progress
        await self.manager.broadcast(WSEvent(
            type=WSEventType.TASK_PROGRESS,
            task_id=self.task.id,
            payload={
                "stage": "starting",
                "message": "Spawning agent...",
                "workspace": str(workspace),
            },
        ))

        self._process = await asyncio.create_subprocess_exec(
            cli, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(workspace),  # SANDBOX: always run inside workspace
        )

        # Start reading output streams
        asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

    async def _read_stdout(self) -> None:
        """Read stdout line by line and feed into parser."""
        assert self._process and self._process.stdout
        try:
            async for line in self._process.stdout:
                if self._disposed:
                    break
                decoded = line.decode("utf-8", errors="replace")
                self._parser.feed(decoded)
        except Exception as e:
            print(f"[Adapter] stdout read error: {e}")
        finally:
            self._parser.flush()
            await self._handle_exit()

    async def _read_stderr(self) -> None:
        """Read stderr and forward as error messages."""
        assert self._process and self._process.stderr
        try:
            async for line in self._process.stderr:
                if self._disposed:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    print(f"[Adapter stderr] {decoded}")
        except Exception:
            pass

    def _handle_message(self, msg: ParsedMessage) -> None:
        """Handle a parsed message from the CLI output (sync callback)."""
        # Schedule async broadcast on the event loop
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            self._handle_message_async(msg),
        )

    async def _handle_message_async(self, msg: ParsedMessage) -> None:
        """Process a parsed message and broadcast to clients."""

        if msg.type == MessageType.TEXT:
            task_msg = TaskMessage(role="assistant", content=msg.content)
            task_repo.add_task_message(self.task.id, task_msg)
            await self.manager.broadcast(WSEvent(
                type=WSEventType.TASK_MESSAGE,
                task_id=self.task.id,
                payload={"role": "assistant", "content": msg.content},
            ))

        elif msg.type == MessageType.SESSION_ID:
            self._session_id = msg.content
            task_repo.update_task_session_id(self.task.id, msg.content)

        elif msg.type == MessageType.TOOL_CALL:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.TOOL_USE,
                task_id=self.task.id,
                payload={"name": msg.content, "input": msg.data.get("input", {})},
            ))

        elif msg.type == MessageType.TOOL_RESULT:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.TOOL_RESULT,
                task_id=self.task.id,
                payload={"content": msg.content},
            ))

        elif msg.type == MessageType.STEP_FINISH:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.STEP_FINISH,
                task_id=self.task.id,
                payload=msg.data,
            ))

        elif msg.type == MessageType.REASONING:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.REASONING,
                task_id=self.task.id,
                payload={"content": msg.content},
            ))

        elif msg.type == MessageType.THOUGHT:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.THOUGHT,
                task_id=self.task.id,
                payload={"content": msg.content},
            ))

        elif msg.type == MessageType.TODO:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.TODO_UPDATE,
                task_id=self.task.id,
                payload=msg.data,
            ))

        elif msg.type == MessageType.ERROR:
            await self.manager.broadcast(WSEvent(
                type=WSEventType.TASK_ERROR,
                task_id=self.task.id,
                payload={"error": msg.content},
            ))

        elif msg.type == MessageType.COMPLETE:
            await self._complete_task(success=True)

    async def _handle_exit(self) -> None:
        """Handle process exit."""
        if self._disposed:
            return

        returncode = self._process.returncode if self._process else -1
        if returncode == 0:
            await self._complete_task(success=True)
        elif returncode is not None:
            await self._complete_task(
                success=False,
                error=f"Process exited with code {returncode}",
            )

    async def _complete_task(self, success: bool, error: str | None = None) -> None:
        """Mark the task as completed."""
        now = datetime.utcnow()
        status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        result = TaskResult(success=success, error=error)

        task_repo.update_task_status(self.task.id, status, now)
        self.task.status = status
        self.task.result = result
        self.task.completed_at = now

        await self.manager.broadcast(WSEvent(
            type=WSEventType.TASK_COMPLETE,
            task_id=self.task.id,
            payload={
                "status": status.value,
                "success": success,
                "error": error,
            },
        ))

    async def cancel(self) -> None:
        """Cancel the running task."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()

        task_repo.update_task_status(self.task.id, TaskStatus.CANCELLED, datetime.utcnow())
        self.task.status = TaskStatus.CANCELLED

    def dispose(self) -> None:
        """Clean up resources."""
        self._disposed = True
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass

    # ── CLI Resolution ────────────────────────────────────────

    def _find_cli(self) -> str | None:
        """Find the opencode CLI binary."""
        # Check common locations
        cli = shutil.which("opencode")
        if cli:
            return cli

        # Check npx
        npx = shutil.which("npx")
        if npx:
            return npx  # Will use npx with args

        return None

    def _build_args(self) -> list[str]:
        """Build CLI arguments for `opencode run "prompt"`.

        Uses the `run` subcommand which accepts a message and exits.
        """
        cli = self._find_cli()
        args: list[str] = []

        # If using npx, prepend the package
        if cli and cli.endswith("npx"):
            args.append("opencode-ai")

        # Use the `run` subcommand with the prompt
        args.append("run")
        args.append(self.task.config.prompt)

        # Model selection: --model provider/model
        if self.task.config.provider_id and self.task.config.model_id:
            args.extend(["--model", f"{self.task.config.provider_id}/{self.task.config.model_id}"])
        elif self.task.config.model_id:
            args.extend(["--model", self.task.config.model_id])

        # Continue session if resuming
        if self.task.session_id:
            args.extend(["--session", self.task.session_id, "--continue"])

        return args

    def _build_env(self) -> dict[str, str]:
        """Build environment variables for the CLI process.

        API keys are passed via env so opencode picks them up automatically.
        """
        env = os.environ.copy()

        # Pass provider/model config via environment
        if self.task.config.provider_id:
            env["OPENCODE_PROVIDER"] = self.task.config.provider_id
        if self.task.config.model_id:
            env["OPENCODE_MODEL"] = self.task.config.model_id

        return env
