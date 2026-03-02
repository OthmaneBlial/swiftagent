"""
Pydantic models for WebSocket events.

Defines the typed JSON messages sent over the WS connection,
replacing Electron IPC events (task:update, thought:stream, permission:request).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WSEventType(str, Enum):
    # Server → Client
    TASK_STARTED = "task:started"
    TASK_MESSAGE = "task:message"
    TASK_PROGRESS = "task:progress"
    TASK_COMPLETE = "task:complete"
    TASK_ERROR = "task:error"
    PERMISSION_REQUEST = "permission:request"
    QUESTION_REQUEST = "question:request"
    THOUGHT = "thought:stream"
    TODO_UPDATE = "todo:update"
    TOOL_USE = "tool:use"
    TOOL_RESULT = "tool:result"
    STEP_FINISH = "step:finish"
    REASONING = "reasoning"

    # Client → Server
    START_TASK = "task:start"
    CANCEL_TASK = "task:cancel"
    PERMISSION_RESPONSE = "permission:response"
    QUESTION_RESPONSE = "question:response"
    RESUME_SESSION = "session:resume"


class WSEvent(BaseModel):
    """A WebSocket event message."""

    type: WSEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PermissionRequest(BaseModel):
    """Request for user permission (file write, command exec, etc)."""

    id: str
    task_id: str
    tool_name: str
    description: str
    file_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionResponse(BaseModel):
    """User response to a permission request."""

    request_id: str
    approved: bool


class TaskProgressPayload(BaseModel):
    """Progress update for a running task."""

    stage: str
    message: str | None = None
    model_name: str | None = None


class StepFinishPayload(BaseModel):
    """Emitted when an LLM step finishes."""

    reason: str
    model: str | None = None
    tokens: dict[str, int] | None = None
    cost: float | None = None
