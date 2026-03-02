"""
REST API routes — replaces Electron IPC handlers.

Ported from base/accomplish/apps/desktop/src/main/ipc/handlers.ts (1385 lines).
Supports all 7 providers: OpenAI, xAI, Anthropic, Gemini, DeepSeek, Z-AI, Ollama.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from swiftagent.models.provider import (
    ConnectedProvider,
    ConnectionStatus,
    DEFAULT_MODELS,
    OllamaConfig,
    PROVIDER_KEY_ENV_VARS,
    PROVIDER_LABELS,
    ProviderCatalogEntry,
    ProviderId,
    SelectedModel,
)
from swiftagent.models.settings import AppSettings
from swiftagent.models.task import Task, TaskConfig
from swiftagent.storage import tasks as task_repo
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import providers as provider_repo
from swiftagent.storage.secure import SecureStorage

router = APIRouter()


def _get_secure_storage(request: Request) -> SecureStorage:
    data_dir = request.app.state.data_dir
    return SecureStorage(storage_path=str(data_dir))


# ═══════════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════════

@router.get("/tasks", response_model=list[Task])
async def list_tasks():
    return task_repo.get_tasks()


@router.get("/tasks/{task_id}", response_model=Task | None)
async def get_task(task_id: str):
    task = task_repo.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    task_repo.delete_task(task_id)
    return {"ok": True}


@router.delete("/tasks")
async def clear_history():
    task_repo.clear_history()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════

@router.get("/settings", response_model=AppSettings)
async def get_settings():
    return settings_repo.get_app_settings()


class SettingsUpdate(BaseModel):
    debug_mode: bool | None = None
    theme: str | None = None
    onboarding_complete: bool | None = None
    selected_model: str | None = None


@router.put("/settings")
async def update_settings(update: SettingsUpdate):
    if update.debug_mode is not None:
        settings_repo.set_debug_mode(update.debug_mode)
    if update.theme is not None:
        settings_repo.set_theme(update.theme)
    if update.onboarding_complete is not None:
        settings_repo.set_onboarding_complete(update.onboarding_complete)
    if update.selected_model is not None:
        settings_repo.set_selected_model(update.selected_model)
    return settings_repo.get_app_settings()


# ═══════════════════════════════════════════════════════════════
# Providers
# ═══════════════════════════════════════════════════════════════

@router.get("/providers")
async def get_providers():
    settings = provider_repo.get_provider_settings()
    return settings


@router.get("/providers/catalog")
async def get_provider_catalog():
    """Return the full provider catalog with labels, env vars, and default models."""
    catalog: list[ProviderCatalogEntry] = []
    for pid in ProviderId:
        catalog.append(ProviderCatalogEntry(
            id=pid.value,
            label=PROVIDER_LABELS.get(pid, pid.value),
            requires_key=pid != ProviderId.OLLAMA,
            key_env_var=PROVIDER_KEY_ENV_VARS.get(pid),
            default_models=DEFAULT_MODELS.get(pid, []),
        ))
    return catalog


@router.get("/providers/models/{provider_id}")
async def get_models(provider_id: str):
    try:
        pid = ProviderId(provider_id)
    except ValueError:
        raise HTTPException(400, f"Unknown provider: {provider_id}")
    return DEFAULT_MODELS.get(pid, [])


@router.post("/providers/{provider_id}/connect")
async def connect_provider(provider_id: str):
    try:
        pid = ProviderId(provider_id)
    except ValueError:
        raise HTTPException(400, f"Unknown provider: {provider_id}")

    provider = ConnectedProvider(
        id=pid,
        status=ConnectionStatus.CONNECTED,
        label=PROVIDER_LABELS.get(pid),
    )
    provider_repo.set_connected_provider(pid, provider)
    return provider


@router.post("/providers/{provider_id}/disconnect")
async def disconnect_provider(provider_id: str):
    try:
        pid = ProviderId(provider_id)
    except ValueError:
        raise HTTPException(400, f"Unknown provider: {provider_id}")
    provider_repo.remove_connected_provider(pid)
    return {"ok": True}


@router.put("/providers/active")
async def set_active_provider(body: SelectedModel):
    provider_repo.set_active_provider(body.provider)
    provider_repo.update_provider_model(body.provider, body.model)
    return {"ok": True}


class OllamaConfigUpdate(BaseModel):
    base_url: str = "http://localhost:11434"
    enabled: bool = True


@router.put("/providers/ollama/config")
async def update_ollama_config(config: OllamaConfigUpdate):
    settings_repo.set_ollama_config(config.model_dump())
    return {"ok": True}


@router.get("/providers/ollama/config")
async def get_ollama_config():
    config = settings_repo.get_ollama_config()
    return config or {"base_url": "http://localhost:11434", "enabled": False}


@router.get("/onboard/status")
async def get_onboard_status(request: Request):
    """Return which providers have API keys configured."""
    secure = _get_secure_storage(request)
    results = []
    for pid in ProviderId:
        if pid == ProviderId.OLLAMA:
            results.append({"id": pid.value, "has_key": True, "source": "local"})
            continue
        key = secure.get_api_key(pid.value)
        results.append({
            "id": pid.value,
            "has_key": key is not None,
            "source": "stored" if key else "none",
        })
    return results


# ═══════════════════════════════════════════════════════════════
# API Keys — all providers that require keys
# ═══════════════════════════════════════════════════════════════

# Providers that support API key storage (all except Ollama)
_KEY_PROVIDERS = {pid.value for pid in ProviderId if pid != ProviderId.OLLAMA}


class ApiKeyBody(BaseModel):
    key: str


@router.post("/keys/{provider}")
async def store_api_key(provider: str, body: ApiKeyBody, request: Request):
    if provider not in _KEY_PROVIDERS:
        raise HTTPException(400, f"API key storage not supported for: {provider}")
    secure = _get_secure_storage(request)
    secure.store_api_key(provider, body.key)
    return {"ok": True}


@router.get("/keys/{provider}")
async def get_api_key(provider: str, request: Request):
    secure = _get_secure_storage(request)
    key = secure.get_api_key(provider)
    # Return masked key for security
    if key:
        masked = key[:8] + "…" + key[-4:]
        return {"provider": provider, "has_key": True, "masked": masked}
    return {"provider": provider, "has_key": False, "masked": None}


@router.delete("/keys/{provider}")
async def delete_api_key(provider: str, request: Request):
    secure = _get_secure_storage(request)
    deleted = secure.delete_api_key(provider)
    return {"ok": deleted}


@router.get("/keys")
async def list_api_keys(request: Request):
    secure = _get_secure_storage(request)
    keys = secure.get_all_api_keys()
    result = []
    for provider_id in _KEY_PROVIDERS:
        key = keys.get(provider_id)
        result.append({
            "provider": provider_id,
            "has_key": key is not None,
        })
    return result
