"""Bounded bidirectional JSONL transport for Codex app-server."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

MAX_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_PENDING_REQUESTS = 128
MAX_SERVER_REQUESTS = 16


class CodexProtocolError(RuntimeError):
    """A malformed frame, RPC error, or broken app-server connection."""


NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
RequestHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
DisconnectHandler = Callable[[str], Awaitable[None]]


class CodexRpcConnection:
    """Small JSON-RPC-like client for app-server's headerless JSONL wire format."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        on_notification: NotificationHandler,
        on_request: RequestHandler,
        on_disconnect: DisconnectHandler,
    ):
        self.reader = reader
        self.writer = writer
        self.on_notification = on_notification
        self.on_request = on_request
        self.on_disconnect = on_disconnect
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._server_tasks: set[asyncio.Task[None]] = set()
        self._write_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._closing = False

    def start(self) -> None:
        if self._reader_task is not None:
            raise RuntimeError("Codex RPC reader already started")
        self._reader_task = asyncio.create_task(self._read_loop())

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30,
    ) -> dict[str, Any]:
        if self._closed:
            raise CodexProtocolError("Codex app-server connection is closed")
        if len(self._pending) >= MAX_PENDING_REQUESTS:
            raise CodexProtocolError("Too many pending Codex app-server requests")
        request_id = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"method": method, "id": request_id, "params": params or {}})
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._closed:
            raise CodexProtocolError("Codex app-server connection is closed")
        await self._send({"method": method, "params": params or {}})

    async def _send(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise CodexProtocolError("Codex app-server message exceeds 2 MiB")
        async with self._write_lock:
            self.writer.write(encoded + b"\n")
            await self.writer.drain()

    async def _read_loop(self) -> None:
        reason = "Codex app-server closed its output stream"
        try:
            while not self._closing:
                line = await self.reader.readline()
                if not line:
                    break
                if len(line) > MAX_MESSAGE_BYTES:
                    raise CodexProtocolError("Codex app-server frame exceeds 2 MiB")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CodexProtocolError("Codex app-server emitted malformed JSON") from exc
                if not isinstance(message, dict):
                    raise CodexProtocolError("Codex app-server frame must be a JSON object")
                await self._dispatch(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            reason = str(exc)
        finally:
            self._closed = True
            error = CodexProtocolError(reason)
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            if not self._closing:
                await self.on_disconnect(reason)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        request_id = message.get("id")
        if method is None and request_id is not None:
            if not isinstance(request_id, int):
                raise CodexProtocolError("Codex response id must be an integer")
            future = self._pending.get(request_id)
            if future is None or future.done():
                return
            error = message.get("error")
            if error is not None:
                detail = error.get("message") if isinstance(error, dict) else str(error)
                future.set_exception(CodexProtocolError(f"Codex RPC request failed: {detail}"))
                return
            result = message.get("result", {})
            if not isinstance(result, dict):
                raise CodexProtocolError("Codex RPC result must be an object")
            future.set_result(result)
            return

        if not isinstance(method, str) or not method or len(method) > 256:
            raise CodexProtocolError("Codex RPC method is invalid")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise CodexProtocolError("Codex RPC params must be an object")
        if request_id is None:
            await self.on_notification(method, params)
            return
        if not isinstance(request_id, (int, str)):
            raise CodexProtocolError("Codex server request id is invalid")
        if len(self._server_tasks) >= MAX_SERVER_REQUESTS:
            await self._send(
                {
                    "id": request_id,
                    "error": {"code": -32001, "message": "Too many pending approval requests"},
                }
            )
            return
        task = asyncio.create_task(self._serve_request(request_id, method, params))
        self._server_tasks.add(task)
        task.add_done_callback(self._server_tasks.discard)

    async def _serve_request(
        self, request_id: int | str, method: str, params: dict[str, Any]
    ) -> None:
        try:
            result = await self.on_request(method, params)
            await self._send({"id": request_id, "result": result})
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await self._send(
                    {"id": request_id, "error": {"code": -32800, "message": "Cancelled"}}
                )
        except Exception as exc:
            with contextlib.suppress(Exception):
                await self._send(
                    {"id": request_id, "error": {"code": -32603, "message": str(exc)[:1_024]}}
                )

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._closed = True
        for task in self._server_tasks:
            task.cancel()
        if self._server_tasks:
            await asyncio.gather(*self._server_tasks, return_exceptions=True)
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        self.writer.close()
        with contextlib.suppress(Exception):
            await self.writer.wait_closed()
