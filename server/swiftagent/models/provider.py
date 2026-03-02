"""
Pydantic models for AI Providers.

Trimmed from 15+ providers to the essential 3: Anthropic, OpenAI, Ollama.
Ported from base/accomplish/packages/agent-core/src/common/types/provider.ts
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProviderId(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


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


# Default models shipped with each provider
DEFAULT_MODELS: dict[ProviderId, list[ModelConfig]] = {
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
            id="claude-3-5-haiku-20241022",
            display_name="Claude 3.5 Haiku",
            provider=ProviderId.ANTHROPIC,
            full_id="anthropic/claude-3-5-haiku-20241022",
            context_window=200000,
            max_output_tokens=8192,
            supports_vision=True,
        ),
    ],
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
    ProviderId.OLLAMA: [],  # Populated dynamically
}
