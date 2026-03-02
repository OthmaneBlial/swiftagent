"""
App settings repository — key-value store in SQLite.

Ported from base/accomplish/packages/agent-core/src/storage/repositories/appSettings.ts
"""

from __future__ import annotations

import json

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


# ── Typed Accessors ───────────────────────────────────────────

def get_debug_mode() -> bool:
    return _get("debug_mode", "0") == "1"

def set_debug_mode(enabled: bool) -> None:
    _set("debug_mode", "1" if enabled else "0")

def get_onboarding_complete() -> bool:
    return _get("onboarding_complete", "0") == "1"

def set_onboarding_complete(complete: bool) -> None:
    _set("onboarding_complete", "1" if complete else "0")

def get_theme() -> str:
    return _get("theme", "system")

def set_theme(theme: str) -> None:
    _set("theme", theme)

def get_selected_model() -> str | None:
    val = _get("selected_model", "")
    return val if val else None

def set_selected_model(model: str) -> None:
    _set("selected_model", model)

def get_ollama_config() -> dict | None:
    raw = _get("ollama_config", "")
    return json.loads(raw) if raw else None

def set_ollama_config(config: dict) -> None:
    _set("ollama_config", json.dumps(config))

def get_app_settings() -> AppSettings:
    return AppSettings(
        debug_mode=get_debug_mode(),
        onboarding_complete=get_onboarding_complete(),
        theme=get_theme(),
        selected_model=get_selected_model(),
    )

def clear_app_settings() -> None:
    db = get_database()
    db.execute("DELETE FROM app_settings")
    db.commit()
