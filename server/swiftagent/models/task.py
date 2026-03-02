"""
Pydantic models for Tasks.

Ported from base/accomplish/packages/agent-core/src/common/types/task.ts
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    WAITING_FOR_QUESTION = "waiting_for_question"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskMessage(BaseModel):
    """A single message in a task's conversation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] | None = None


class TaskAttachment(BaseModel):
    """File attached to a task prompt."""

    name: str
    path: str
    size: int | None = None
    mime_type: str | None = None


class TaskConfig(BaseModel):
    """Configuration to start a new task."""

    prompt: str
    working_directory: str | None = None
    attachments: list[TaskAttachment] = Field(default_factory=list)
    provider_id: str | None = None
    model_id: str | None = None


class TaskResult(BaseModel):
    """Result of a completed task."""

    success: bool
    summary: str | None = None
    error: str | None = None


class Task(BaseModel):
    """A task managed by SwiftAgent."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    config: TaskConfig
    status: TaskStatus = TaskStatus.PENDING
    messages: list[TaskMessage] = Field(default_factory=list)
    result: TaskResult | None = None
    session_id: str | None = None
    summary: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class TodoItem(BaseModel):
    """A checklist/todo item reported by the agent."""

    id: str
    content: str
    completed: bool = False
