"""
Pydantic models for App Settings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AppSettings(BaseModel):
    """Application-level settings."""

    debug_mode: bool = False
    theme: Literal["light", "dark", "system"] = "system"
    default_agent_id: str = "claude-code"
    claude_model: str | None = None
    claude_permission_mode: str = "default"
    claude_cli_path: str | None = None
    acp_command_json: str = ""
    codex_model: str | None = None
    codex_cli_path: str | None = None
    codex_approval_policy: Literal["untrusted", "on-request", "never"] = "on-request"
    codex_sandbox_mode: Literal["read-only", "workspace-write", "danger-full-access"] = (
        "workspace-write"
    )
    codex_allow_dangerous_bypass: bool = False
    opencode_model: str | None = None
    opencode_cli_path: str | None = None
    workspace_dir: str
    sandbox_mode: Literal["strict", "fallback"] = "strict"
