"""Claude Code settings stored in SwiftAgent's generic key-value repository."""

from __future__ import annotations

import os

from swiftagent.storage import settings as settings_repo


def get_model() -> str | None:
    value = settings_repo.get_value("claude_model", os.environ.get("CLAUDE_MODEL", "")).strip()
    return value or None


def set_model(model: str | None) -> None:
    settings_repo.set_value("claude_model", (model or "").strip())


def get_permission_mode() -> str:
    default_mode = os.environ.get("CLAUDE_PERMISSION_MODE", "default")
    return settings_repo.get_value("claude_permission_mode", default_mode)


def set_permission_mode(mode: str) -> None:
    settings_repo.set_value("claude_permission_mode", mode)


def get_cli_path() -> str | None:
    value = settings_repo.get_value(
        "claude_cli_path", os.environ.get("SWIFTAGENT_CLAUDE_PATH", "")
    ).strip()
    return value or None


def set_cli_path(path: str | None) -> None:
    settings_repo.set_value("claude_cli_path", (path or "").strip())
