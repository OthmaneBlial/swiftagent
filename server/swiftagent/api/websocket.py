"""
WebSocket handler for real-time task streaming.

Replaces Electron IPC events (task:update, thought:stream, permission:request)
with a single WS endpoint using typed JSON messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from swiftagent.models.agent import AgentEvent
from swiftagent.models.events import WSEvent, WSEventType
from swiftagent.models.task import TaskConfig

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_WS_MESSAGE_BYTES = 256 * 1024


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._pending_permissions: dict[str, asyncio.Future] = {}
        self._pending_questions: dict[str, asyncio.Future] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("ws_connected connections=%s", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("ws_disconnected connections=%s", len(self._connections))

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

    async def broadcast_agent_event(self, event: AgentEvent) -> None:
        """Persist, then broadcast, the versioned agent-neutral event envelope."""
        from swiftagent.storage import receipts as receipt_repo
        from swiftagent.storage.database import is_initialized

        if is_initialized():
            try:
                receipt_repo.add_agent_event(event)
            except sqlite3.Error:
                # A storage failure must not break the adapter process or other
                # live tasks. The server log still makes the evidence gap clear.
                logger.exception(
                    "agent_event_persistence_failed task_id=%s event_type=%s",
                    event.run_id,
                    event.type.value,
                )
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
        except TimeoutError:
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
        except TimeoutError:
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
            if len(raw.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                await manager.send(
                    ws,
                    WSEvent(
                        type=WSEventType.TASK_ERROR,
                        payload={
                            "error": "Message is too large. Keep task prompts below 50,000 characters."
                        },
                    ),
                )
                continue
            try:
                data = json.loads(raw)
                event_type = data.get("type")
                payload = data.get("payload", {})
                task_id = data.get("task_id")
                if not isinstance(payload, dict):
                    raise ValueError("Event payload must be a JSON object")
                await _handle_client_event(ws, event_type, payload, task_id)
            except json.JSONDecodeError:
                await manager.send(
                    ws,
                    WSEvent(
                        type=WSEventType.TASK_ERROR,
                        payload={"error": "Invalid JSON"},
                    ),
                )
            except (ValidationError, ValueError) as exc:
                await manager.send(
                    ws,
                    WSEvent(
                        type=WSEventType.TASK_ERROR,
                        task_id=task_id if isinstance(task_id, str) else None,
                        payload={"error": str(exc)},
                    ),
                )
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logger.exception("websocket_error error=%s", e)
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
        await manager.send(
            ws,
            WSEvent(
                type=WSEventType.TASK_STARTED,
                task_id=task.id,
                payload=task.model_dump(),
            ),
        )

    elif event_type == WSEventType.CANCEL_TASK.value:
        from swiftagent.engine.manager import task_manager

        if not task_id:
            raise ValueError("task_id is required to cancel a task")
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
        agent_id = payload.get("agent_id", "claude-code")
        if not isinstance(agent_id, str):
            raise ValueError("agent_id must be a string")
        task = await task_manager.resume_session(
            session_id,
            prompt,
            manager,
            agent_id=agent_id,
        )
        await manager.send(
            ws,
            WSEvent(
                type=WSEventType.TASK_STARTED,
                task_id=task.id,
                payload=task.model_dump(),
            ),
        )
    else:
        raise ValueError("Unsupported WebSocket event type")
