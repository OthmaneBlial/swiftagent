"""
Provider settings repository.

Ported from base/accomplish/packages/agent-core/src/storage/repositories/providerSettings.ts
Simplified to 3 providers: Anthropic, OpenAI, Ollama.
"""

from __future__ import annotations

import json

from swiftagent.models.provider import (
    ConnectedProvider,
    ConnectionStatus,
    ProviderId,
    ProviderSettings,
)
from swiftagent.storage.database import get_database


def _get_json(key: str) -> dict | None:
    db = get_database()
    row = db.execute("SELECT value_json FROM provider_settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else None


def _set_json(key: str, value: dict) -> None:
    db = get_database()
    db.execute(
        "INSERT OR REPLACE INTO provider_settings (key, value_json) VALUES (?, ?)",
        (key, json.dumps(value)),
    )
    db.commit()


def get_provider_settings() -> ProviderSettings:
    active = _get_json("active_provider")
    connected = _get_json("connected_providers") or {}

    parsed_connected: dict[str, ConnectedProvider] = {}
    for pid, data in connected.items():
        try:
            parsed_connected[pid] = ConnectedProvider(**data)
        except Exception:
            continue

    return ProviderSettings(
        active_provider=ProviderId(active["id"]) if active else None,
        connected_providers=parsed_connected,
    )


def set_active_provider(provider_id: ProviderId) -> None:
    _set_json("active_provider", {"id": provider_id.value})


def get_active_provider_id() -> ProviderId | None:
    data = _get_json("active_provider")
    if not data:
        return None
    try:
        return ProviderId(data["id"])
    except ValueError:
        return None


def get_connected_provider(provider_id: ProviderId) -> ConnectedProvider | None:
    connected = _get_json("connected_providers") or {}
    data = connected.get(provider_id.value)
    if not data:
        return None
    return ConnectedProvider(**data)


def set_connected_provider(provider_id: ProviderId, provider: ConnectedProvider) -> None:
    connected = _get_json("connected_providers") or {}
    connected[provider_id.value] = provider.model_dump()
    _set_json("connected_providers", connected)


def remove_connected_provider(provider_id: ProviderId) -> None:
    connected = _get_json("connected_providers") or {}
    connected.pop(provider_id.value, None)
    _set_json("connected_providers", connected)


def update_provider_model(provider_id: ProviderId, model_id: str) -> None:
    connected = _get_json("connected_providers") or {}
    if provider_id.value in connected:
        connected[provider_id.value]["selected_model"] = model_id
        _set_json("connected_providers", connected)


def get_connected_provider_ids() -> list[str]:
    connected = _get_json("connected_providers") or {}
    return list(connected.keys())


def has_ready_provider() -> bool:
    connected = _get_json("connected_providers") or {}
    return any(
        p.get("status") == ConnectionStatus.CONNECTED.value
        for p in connected.values()
    )


def clear_provider_settings() -> None:
    db = get_database()
    db.execute("DELETE FROM provider_settings")
    db.commit()
