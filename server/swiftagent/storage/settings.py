"""
App settings repository — key-value store in SQLite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from swiftagent.models.settings import AppSettings
from swiftagent.storage.database import get_database


def _get(key: str, default: str = "") -> str:
    db = get_database()
    row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set(key: str, value: str) -> None:
    db = get_database()
    db.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    db.commit()


def get_value(key: str, default: str = "") -> str:
    """Read an adapter-owned setting from the shared key-value store."""
    return _get(key, default)


def set_value(key: str, value: str) -> None:
    """Persist an adapter-owned setting without teaching storage about its meaning."""
    _set(key, value)


def _default_workspace_dir() -> str:
    configured = os.environ.get("SWIFTAGENT_WORKSPACE_DIR", "").strip()
    if configured:
        return configured

    data_dir = os.environ.get("SWIFTAGENT_DATA_DIR", "").strip()
    if data_dir:
        return str(Path(data_dir) / "workspace")

    return str(Path.home() / ".swiftagent" / "workspace")


# ── Typed accessors ───────────────────────────────────────────


def get_debug_mode() -> bool:
    return _get("debug_mode", "0") == "1"


def set_debug_mode(enabled: bool) -> None:
    _set("debug_mode", "1" if enabled else "0")


def get_theme() -> str:
    value = _get("theme", "system").strip().lower()
    if value in {"light", "dark", "system"}:
        return value
    return "system"


def set_theme(theme: str) -> None:
    normalized = theme.strip().lower()
    if normalized not in {"light", "dark", "system"}:
        normalized = "system"
    _set("theme", normalized)


def get_default_agent_id() -> str:
    return _get("default_agent_id", "claude-code").strip() or "claude-code"


def set_default_agent_id(agent_id: str) -> None:
    _set("default_agent_id", agent_id.strip())


def get_claude_model() -> str | None:
    value = _get("claude_model", os.environ.get("CLAUDE_MODEL", "")).strip()
    return value or None


def set_claude_model(model: str | None) -> None:
    _set("claude_model", (model or "").strip())


def get_claude_permission_mode() -> str:
    default_mode = os.environ.get("CLAUDE_PERMISSION_MODE", "default")
    return _get("claude_permission_mode", default_mode)


def set_claude_permission_mode(mode: str) -> None:
    _set("claude_permission_mode", mode)


def get_claude_cli_path() -> str | None:
    value = _get("claude_cli_path", os.environ.get("SWIFTAGENT_CLAUDE_PATH", "")).strip()
    return value or None


def set_claude_cli_path(path: str | None) -> None:
    _set("claude_cli_path", (path or "").strip())


def get_workspace_dir() -> str:
    return _get("workspace_dir", _default_workspace_dir())


def set_workspace_dir(path: str) -> None:
    _set("workspace_dir", path.strip())


def get_sandbox_mode() -> str:
    configured = _get("sandbox_mode", "").strip()
    if configured in {"strict", "fallback"}:
        return configured
    fallback = os.environ.get("SWIFTAGENT_SANDBOX_MODE", "strict").strip()
    return fallback if fallback in {"strict", "fallback"} else "strict"


def set_sandbox_mode(mode: str) -> None:
    normalized = mode.strip().lower()
    if normalized not in {"strict", "fallback"}:
        normalized = "strict"
    _set("sandbox_mode", normalized)


def get_app_settings() -> AppSettings:
    acp_command_raw = _get(
        "acp_command_json", os.environ.get("SWIFTAGENT_ACP_COMMAND_JSON", "")
    ).strip()
    try:
        acp_command_value = json.loads(acp_command_raw) if acp_command_raw else []
    except json.JSONDecodeError:
        acp_command_value = acp_command_raw
    if isinstance(acp_command_value, list):
        normalized_acp_command = (
            json.dumps(acp_command_value, ensure_ascii=False) if acp_command_value else ""
        )
    else:
        normalized_acp_command = acp_command_raw
    return AppSettings(
        debug_mode=get_debug_mode(),
        theme=get_theme(),
        default_agent_id=get_default_agent_id(),
        claude_model=get_claude_model(),
        claude_permission_mode=get_claude_permission_mode(),
        claude_cli_path=get_claude_cli_path(),
        acp_command_json=normalized_acp_command,
        codex_model=_get("codex_model", "").strip() or None,
        codex_cli_path=_get(
            "codex_cli_path", os.environ.get("SWIFTAGENT_CODEX_PATH", "")
        ).strip()
        or None,
        codex_approval_policy=_get("codex_approval_policy", "on-request"),
        codex_sandbox_mode=_get("codex_sandbox_mode", "workspace-write"),
        codex_allow_dangerous_bypass=(
            _get("codex_allow_dangerous_bypass", "0") == "1"
        ),
        workspace_dir=get_workspace_dir(),
        sandbox_mode=get_sandbox_mode(),
    )


def clear_app_settings() -> None:
    db = get_database()
    db.execute("DELETE FROM app_settings")
    db.commit()
