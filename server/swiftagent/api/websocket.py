"""
WebSocket handler for real-time task streaming.

Replaces Electron IPC events (task:update, thought:stream, permission:request)
with a single WS endpoint using typed JSON messages.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from swiftagent.models.events import (
    PermissionResponse,
    WSEvent,
    WSEventType,
)
from swiftagent.models.task import Task, TaskConfig, TaskStatus

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._pending_permissions: dict[str, asyncio.Future] = {}
        self._pending_questions: dict[str, asyncio.Future] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        print(f"[WS] Client connected ({len(self._connections)} total)")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        print(f"[WS] Client disconnected ({len(self._connections)} total)")

    async def broadcast(self, event: WSEvent) -> None:
        """Send an event to all connected clients."""
        data = event.model_dump_json()
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    async def send(self, ws: WebSocket, event: WSEvent) -> None:
        await ws.send_text(event.model_dump_json())

    # ── Permission Flow ───────────────────────────────────────

    async def request_permission(self, request_id: str, event: WSEvent) -> bool:
        """Broadcast a permission request and wait for user response."""
        future: asyncio.Future[bool] = asyncio.get_event_loop().create_future()
        self._pending_permissions[request_id] = future
        await self.broadcast(event)
        try:
            return await asyncio.wait_for(future, timeout=300)  # 5 min timeout
        except asyncio.TimeoutError:
            return False
        finally:
            self._pending_permissions.pop(request_id, None)

    def resolve_permission(self, request_id: str, approved: bool) -> None:
        future = self._pending_permissions.get(request_id)
        if future and not future.done():
            future.set_result(approved)

    # ── Question Flow ─────────────────────────────────────────

    async def request_question(self, request_id: str, event: WSEvent) -> str:
        """Broadcast a question and wait for user answer."""
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_questions[request_id] = future
        await self.broadcast(event)
        try:
            return await asyncio.wait_for(future, timeout=600)  # 10 min timeout
        except asyncio.TimeoutError:
            return ""
        finally:
            self._pending_questions.pop(request_id, None)

    def resolve_question(self, request_id: str, answer: str) -> None:
        future = self._pending_questions.get(request_id)
        if future and not future.done():
            future.set_result(answer)


# Singleton manager
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
                event_type = data.get("type")
                payload = data.get("payload", {})
                task_id = data.get("task_id")

                await _handle_client_event(ws, event_type, payload, task_id)
            except json.JSONDecodeError:
                await manager.send(ws, WSEvent(
                    type=WSEventType.TASK_ERROR,
                    payload={"error": "Invalid JSON"},
                ))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        print(f"[WS] Error: {e}")
        traceback.print_exc()
        manager.disconnect(ws)


async def _handle_client_event(
    ws: WebSocket,
    event_type: str | None,
    payload: dict,
    task_id: str | None,
) -> None:
    """Handle an incoming client WebSocket event."""

    if event_type == WSEventType.START_TASK.value:
        # Task start is handled via REST POST /api/tasks
        # but we can also support it over WS for convenience
        from swiftagent.engine.manager import task_manager
        config = TaskConfig(**payload)
        task = await task_manager.start_task(config, manager)
        await manager.send(ws, WSEvent(
            type=WSEventType.TASK_STARTED,
            task_id=task.id,
            payload=task.model_dump(),
        ))

    elif event_type == WSEventType.CANCEL_TASK.value:
        from swiftagent.engine.manager import task_manager
        if task_id:
            await task_manager.cancel_task(task_id)

    elif event_type == WSEventType.PERMISSION_RESPONSE.value:
        request_id = payload.get("request_id", "")
        approved = payload.get("approved", False)
        manager.resolve_permission(request_id, approved)

    elif event_type == WSEventType.QUESTION_RESPONSE.value:
        request_id = payload.get("request_id", "")
        answer = payload.get("answer", "")
        manager.resolve_question(request_id, answer)

    elif event_type == WSEventType.RESUME_SESSION.value:
        from swiftagent.engine.manager import task_manager
        session_id = payload.get("session_id", "")
        prompt = payload.get("prompt", "")
        task = await task_manager.resume_session(session_id, prompt, manager)
        await manager.send(ws, WSEvent(
            type=WSEventType.TASK_STARTED,
            task_id=task.id,
            payload=task.model_dump(),
        ))
