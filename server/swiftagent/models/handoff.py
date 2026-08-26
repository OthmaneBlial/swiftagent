"""Explicit, redacted cross-agent handoff contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from swiftagent.models.receipt import VerificationStatus


class HandoffPreviewRequest(BaseModel):
    target_agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    target_model_id: str | None = Field(default=None, max_length=256)
    include_intent: bool = True
    include_summary: bool = True
    include_changed_files: bool = True
    include_diff_summary: bool = True
    include_verification: bool = True
    include_unresolved_questions: bool = True
    approved_summary: str | None = Field(default=None, max_length=20_000)
    summary_approved: bool = False
    user_instructions: str | None = Field(default=None, max_length=20_000)


class HandoffVerification(BaseModel):
    status: VerificationStatus
    summary: str | None = None
    command: str | None = None


class HandoffContent(BaseModel):
    original_intent: str | None = None
    approved_summary: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    diff_summary: str | None = None
    verification: HandoffVerification | None = None
    unresolved_questions: list[str] = Field(default_factory=list)
    user_instructions: str | None = None


class HandoffRedaction(BaseModel):
    category: Literal[
        "credential",
        "native_session_id",
        "environment_dump",
        "sensitive_path",
        "content_truncated",
    ]
    replacements: int = Field(ge=1)
    explanation: str


class HandoffPreview(BaseModel):
    schema_version: Literal[1] = 1
    id: str
    source_run_id: str
    source_agent_id: str
    source_agent_name: str
    target_agent_id: str
    target_agent_name: str
    target_model_id: str | None = None
    content: HandoffContent
    rendered_prompt: str
    redactions: list[HandoffRedaction] = Field(default_factory=list)
    excluded_by_design: list[str] = Field(default_factory=list)
    status: Literal["prepared", "starting", "started", "failed"] = "prepared"
    created_at: datetime
    expires_at: datetime


class HandoffRecord(BaseModel):
    id: str
    source_task_id: str
    target_task_id: str | None = None
    target_agent_id: str
    target_model_id: str | None = None
    content: HandoffContent
    prompt_text: str
    redactions: list[HandoffRedaction]
    excluded_by_design: list[str]
    status: Literal["prepared", "starting", "started", "failed"]
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    error: str | None = None
