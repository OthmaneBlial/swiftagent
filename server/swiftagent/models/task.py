"""
Pydantic models for Tasks.

Ported from base/accomplish/packages/agent-core/src/common/types/task.ts
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_PROMPT_CHARS = 50_000
MAX_ATTACHMENTS = 32


class TaskStatus(StrEnum):
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] | None = None


class TaskAttachment(BaseModel):
    """File attached to a task prompt."""

    name: str
    path: str
    size: int | None = None
    mime_type: str | None = None


class TaskConfig(BaseModel):
    """Configuration to start a new task."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    agent_id: str = Field(default="claude-code", pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    working_directory: str | None = Field(default=None, max_length=4_096)
    attachments: list[TaskAttachment] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)
    model_id: str | None = Field(default=None, max_length=256)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt cannot be empty")
        return normalized

    @field_validator("working_directory", "model_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


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
    agent_id: str = "claude-code"
    adapter_id: str = "claude-stream-json"
    adapter_version: str = "0.3.0"
    native_session_id: str | None = None
    capability_snapshot: dict[str, Any] = Field(default_factory=dict)
    # Kept through v0.x for API compatibility; mirrors native_session_id.
    session_id: str | None = None
    summary: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class TodoItem(BaseModel):
    """A checklist/todo item reported by the agent."""

    id: str
    content: str
    completed: bool = False
