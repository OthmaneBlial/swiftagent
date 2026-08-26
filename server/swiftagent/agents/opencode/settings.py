"""OpenCode adapter settings owned by the adapter."""

from __future__ import annotations

import os

from swiftagent.storage import settings as settings_repo


def get_cli_path() -> str | None:
    value = settings_repo.get_value(
        "opencode_cli_path", os.environ.get("SWIFTAGENT_OPENCODE_PATH", "")
    ).strip()
    return value or None


def set_cli_path(path: str | None) -> None:
    settings_repo.set_value("opencode_cli_path", (path or "").strip())


def get_model() -> str | None:
    value = settings_repo.get_value("opencode_model", "").strip()
    return value or None


def set_model(model: str | None) -> None:
    settings_repo.set_value("opencode_model", (model or "").strip())
