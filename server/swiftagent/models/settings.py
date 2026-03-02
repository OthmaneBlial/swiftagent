"""
Pydantic models for App Settings.
"""

from __future__ import annotations

from pydantic import BaseModel


class AppSettings(BaseModel):
    """Application-level settings."""

    debug_mode: bool = False
    onboarding_complete: bool = False
    theme: str = "system"  # "light" | "dark" | "system"
    selected_model: str | None = None
