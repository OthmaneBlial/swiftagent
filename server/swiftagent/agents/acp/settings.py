"""Safe literal-command configuration for the standalone ACP adapter."""

from __future__ import annotations

import json
import os

from swiftagent.storage import settings as settings_repo

ACP_COMMAND_KEY = "acp_command_json"


def parse_command(raw: str) -> list[str] | None:
    """Validate a JSON-encoded literal argv without mutating settings."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ACP command must be a JSON array of literal arguments") from exc
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError("ACP command must be a non-empty JSON array of strings")
    if len(value) > 64 or any(not item or len(item) > 4_096 for item in value):
        raise ValueError("ACP command exceeds the safe argument limits")
    return value


def get_command() -> list[str] | None:
    raw = settings_repo.get_value(
        ACP_COMMAND_KEY,
        os.environ.get("SWIFTAGENT_ACP_COMMAND_JSON", ""),
    )
    return parse_command(raw)


def set_command(command: list[str] | None) -> None:
    settings_repo.set_value(ACP_COMMAND_KEY, json.dumps(command or []))
