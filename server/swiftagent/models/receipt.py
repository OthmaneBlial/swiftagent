"""Versioned, agent-neutral Local Run Receipt models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from swiftagent.models.task import TaskResult

VerificationStatus = Literal["passed", "failed", "not_run"]
EvidenceSource = Literal["user", "adapter", "system"]


class VerificationEvidence(BaseModel):
    """Explicit evidence only; assistant prose is never promoted to verification."""

    status: VerificationStatus = "not_run"
    summary: str | None = Field(default=None, max_length=4_096)
    command: str | None = Field(default=None, max_length=4_096)
    source: EvidenceSource = "user"
    recorded_at: datetime


class ReceiptAgent(BaseModel):
    agent_id: str
    display_name: str
    adapter_id: str
    adapter_version: str
    protocol: str
    model: str | None = None
    native_session_id: str | None = None


class SafetyLayer(BaseModel):
    supported: bool | None = None
    mode: str | None = None
    permission_policy: str | None = None
    active: bool | None = None
    evidence_status: Literal["verified", "partial", "unsupported", "unknown"] = "unknown"
    notice: str | None = None


class ReceiptSafety(BaseModel):
    native: SafetyLayer
    swiftagent_isolation: SafetyLayer
    effective_summary: str


class ActivityLedgerEntry(BaseModel):
    sequence: int
    type: str
    timestamp: datetime
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    native_event_type: str | None = None
    native_metadata: dict[str, Any] = Field(default_factory=dict)


class ReceiptInteractions(BaseModel):
    tools_started: int = 0
    tools_completed: int = 0
    approvals_requested: int = 0
    approvals_approved: int = 0
    approvals_denied: int = 0
    questions_requested: int = 0
    latest_plan: dict[str, Any] | None = None
    latest_usage: dict[str, Any] | None = None


class GitState(BaseModel):
    available: bool = False
    repo_root: str | None = None
    head_sha: str | None = None
    branch: str | None = None
    dirty: bool = False
    changed_files: list[str] = Field(default_factory=list)
    diff_summary: str | None = None
    captured_at: datetime
    error: str | None = None


class ReceiptGitImpact(BaseModel):
    available: bool = False
    baseline_sha: str | None = None
    final_sha: str | None = None
    branch: str | None = None
    initial_dirty: bool = False
    initial_changed_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    post_run_diff_summary: str | None = None
    error: str | None = None


class ReceiptActions(BaseModel):
    inspect: bool = True
    resume_same_agent: bool = False
    create_handoff: bool = False


class RunReceipt(BaseModel):
    """Comparable evidence envelope that keeps native event detail available."""

    schema_version: Literal[1] = 1
    run_id: str
    intent: str
    status: str
    agent: ReceiptAgent
    workspace: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    result: TaskResult | None = None
    safety: ReceiptSafety
    interactions: ReceiptInteractions
    git: ReceiptGitImpact
    verification: VerificationEvidence
    ledger: list[ActivityLedgerEntry] = Field(default_factory=list)
    ledger_total: int = 0
    actions: ReceiptActions
