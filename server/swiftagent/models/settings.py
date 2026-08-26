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
    workspace_dir: str
    sandbox_mode: Literal["strict", "fallback"] = "strict"
