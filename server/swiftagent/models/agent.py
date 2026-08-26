"""Agent identities, capabilities, status, and normalized run events."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentCapabilities(BaseModel):
    """Features an adapter has proved it can expose to SwiftAgent."""

    structured_streaming: bool = False
    session_create: bool = True
    session_resume: bool = False
    session_fork: bool = False
    tool_events: bool = False
    approvals: bool = False
    questions: bool = False
    plan_updates: bool = False
    attachments: bool = False
    attachment_types: list[str] = Field(default_factory=list)
    model_discovery: bool = False
    mode_discovery: bool = False
    usage: bool = False
    native_sandbox: bool = False
    external_sandbox: Literal["verified", "partial", "unsupported", "unknown"] = "unknown"
    cancellation: bool = True


class AgentDefinition(BaseModel):
    """Stable metadata for one registered SwiftAgent integration."""

    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    adapter_version: str = Field(min_length=1, max_length=64)
    protocol: str = Field(min_length=1, max_length=64)
    install_url: str | None = None
    documentation_url: str | None = None
    capabilities: AgentCapabilities


class AgentModelOption(BaseModel):
    """One adapter-discovered provider/model identifier safe to show in the UI."""

    id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    provider: str | None = Field(default=None, max_length=128)


class AgentStatus(BaseModel):
    """Read-only discovery result for an installed coding agent."""

    agent_id: str
    display_name: str
    adapter_id: str
    adapter_version: str
    protocol: str
    install_url: str | None = None
    documentation_url: str | None = None
    installed: bool
    executable_path: str | None = Field(default=None, max_length=4_096)
    version: str | None = Field(default=None, max_length=256)
    compatible: bool | None = None
    auth_status: Literal["not_checked", "ready", "action_required", "unknown", "error"] = (
        "not_checked"
    )
    detail: str | None = Field(default=None, max_length=1_024)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    capabilities: AgentCapabilities
    models: list[AgentModelOption] = Field(default_factory=list, max_length=256)


class AgentEventType(StrEnum):
    """Small stable vocabulary emitted by every adapter."""

    RUN_STARTED = "run.started"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"
    TOOL_STARTED = "tool.started"
    TOOL_UPDATED = "tool.updated"
    TOOL_COMPLETED = "tool.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    QUESTION_REQUESTED = "question.requested"
    QUESTION_RESOLVED = "question.resolved"
    PLAN_UPDATED = "plan.updated"
    USAGE_UPDATED = "usage.updated"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class AgentEvent(BaseModel):
    """Versioned agent-neutral event retained alongside native metadata."""

    schema_version: Literal[1] = 1
    type: AgentEventType
    agent_id: str
    adapter_id: str
    run_id: str
    native_session_id: str | None = None
    native_event_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    native_metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
