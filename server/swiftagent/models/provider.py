"""
Pydantic models for AI Providers.

Supports 7 providers: OpenAI, xAI, Anthropic, Gemini, DeepSeek, Z-AI, Ollama.
Inspired by LightClaw's multi-provider architecture.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProviderId(str, Enum):
    OPENAI = "openai"
    XAI = "xai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    ZAI = "zai"
    OLLAMA = "ollama"


# Display labels for each provider
PROVIDER_LABELS: dict[ProviderId, str] = {
    ProviderId.OPENAI: "OpenAI",
    ProviderId.XAI: "xAI (Grok)",
    ProviderId.ANTHROPIC: "Anthropic (Claude)",
    ProviderId.GEMINI: "Google Gemini",
    ProviderId.DEEPSEEK: "DeepSeek",
    ProviderId.ZAI: "Z-AI (GLM)",
    ProviderId.OLLAMA: "Ollama (Local)",
}

# Environment variable names for API keys
PROVIDER_KEY_ENV_VARS: dict[ProviderId, str] = {
    ProviderId.OPENAI: "OPENAI_API_KEY",
    ProviderId.XAI: "XAI_API_KEY",
    ProviderId.ANTHROPIC: "ANTHROPIC_API_KEY",
    ProviderId.GEMINI: "GEMINI_API_KEY",
    ProviderId.DEEPSEEK: "DEEPSEEK_API_KEY",
    ProviderId.ZAI: "ZAI_API_KEY",
    # Ollama: no API key needed (local)
}

# Extra env vars for Anthropic subscription-style auth
ANTHROPIC_EXTRA_ENV_VARS = {
    "auth_token": "ANTHROPIC_AUTH_TOKEN",
    "base_url": "ANTHROPIC_BASE_URL",
}


class ModelConfig(BaseModel):
    """Configuration for a single AI model."""

    id: str
    display_name: str
    provider: ProviderId
    full_id: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_vision: bool = False


class SelectedModel(BaseModel):
    """Currently selected model for task execution."""

    provider: ProviderId
    model: str
    base_url: str | None = None


class OllamaModelInfo(BaseModel):
    """Info about an available Ollama model."""

    id: str
    display_name: str
    size: int
    tool_support: str = "unknown"  # "supported" | "unsupported" | "unknown"


class OllamaConfig(BaseModel):
    """Ollama provider configuration."""

    base_url: str = "http://localhost:11434"
    enabled: bool = False
    last_validated: float | None = None
    models: list[OllamaModelInfo] = Field(default_factory=list)


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ConnectedProvider(BaseModel):
    """A provider that has been configured/connected."""

    id: ProviderId
    status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    selected_model: str | None = None
    label: str | None = None


class ProviderSettings(BaseModel):
    """All provider settings."""

    active_provider: ProviderId | None = None
    connected_providers: dict[str, ConnectedProvider] = Field(default_factory=dict)


class ProviderCatalogEntry(BaseModel):
    """Catalog entry returned by the /providers/catalog endpoint."""

    id: str
    label: str
    requires_key: bool
    key_env_var: str | None
    default_models: list[ModelConfig]


# ═══════════════════════════════════════════════════════════════
# Default models shipped with each provider
# ═══════════════════════════════════════════════════════════════

DEFAULT_MODELS: dict[ProviderId, list[ModelConfig]] = {
    ProviderId.OPENAI: [
        ModelConfig(
            id="gpt-4o",
            display_name="GPT-4o",
            provider=ProviderId.OPENAI,
            full_id="openai/gpt-4o",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
        ),
        ModelConfig(
            id="gpt-4o-mini",
            display_name="GPT-4o Mini",
            provider=ProviderId.OPENAI,
            full_id="openai/gpt-4o-mini",
            context_window=128000,
            max_output_tokens=16384,
            supports_vision=True,
        ),
    ],
    ProviderId.XAI: [
        ModelConfig(
            id="grok-3",
            display_name="Grok 3",
            provider=ProviderId.XAI,
            full_id="xai/grok-3",
            context_window=131072,
            max_output_tokens=16384,
        ),
        ModelConfig(
            id="grok-3-mini",
            display_name="Grok 3 Mini",
            provider=ProviderId.XAI,
            full_id="xai/grok-3-mini",
            context_window=131072,
            max_output_tokens=16384,
        ),
    ],
    ProviderId.ANTHROPIC: [
        ModelConfig(
            id="claude-sonnet-4-20250514",
            display_name="Claude Sonnet 4",
            provider=ProviderId.ANTHROPIC,
            full_id="anthropic/claude-sonnet-4-20250514",
            context_window=200000,
            max_output_tokens=16384,
            supports_vision=True,
        ),
        ModelConfig(
            id="claude-opus-4-5",
            display_name="Claude Opus 4.5",
            provider=ProviderId.ANTHROPIC,
            full_id="anthropic/claude-opus-4-5",
            context_window=200000,
            max_output_tokens=16384,
            supports_vision=True,
        ),
        ModelConfig(
            id="claude-3-5-haiku-20241022",
            display_name="Claude 3.5 Haiku",
            provider=ProviderId.ANTHROPIC,
            full_id="anthropic/claude-3-5-haiku-20241022",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
        ),
    ],
    ProviderId.GEMINI: [
        ModelConfig(
            id="gemini-2.5-flash",
            display_name="Gemini 2.5 Flash",
            provider=ProviderId.GEMINI,
            full_id="gemini/gemini-2.5-flash",
            context_window=1048576,
            max_output_tokens=65536,
            supports_vision=True,
        ),
        ModelConfig(
            id="gemini-2.5-pro",
            display_name="Gemini 2.5 Pro",
            provider=ProviderId.GEMINI,
            full_id="gemini/gemini-2.5-pro",
            context_window=1048576,
            max_output_tokens=65536,
            supports_vision=True,
        ),
    ],
    ProviderId.DEEPSEEK: [
        ModelConfig(
            id="deepseek-chat",
            display_name="DeepSeek Chat",
            provider=ProviderId.DEEPSEEK,
            full_id="deepseek/deepseek-chat",
            context_window=128000,
            max_output_tokens=8192,
        ),
        ModelConfig(
            id="deepseek-reasoner",
            display_name="DeepSeek Reasoner",
            provider=ProviderId.DEEPSEEK,
            full_id="deepseek/deepseek-reasoner",
            context_window=128000,
            max_output_tokens=8192,
        ),
    ],
    ProviderId.ZAI: [
        ModelConfig(
            id="glm-4-plus",
            display_name="GLM-4 Plus",
            provider=ProviderId.ZAI,
            full_id="zai/glm-4-plus",
            context_window=128000,
            max_output_tokens=8192,
        ),
        ModelConfig(
            id="glm-4",
            display_name="GLM-4",
            provider=ProviderId.ZAI,
            full_id="zai/glm-4",
            context_window=128000,
            max_output_tokens=8192,
        ),
    ],
    ProviderId.OLLAMA: [],  # Populated dynamically
}
