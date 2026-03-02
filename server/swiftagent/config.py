"""
Environment-based configuration loader.

Parses .env files (no python-dotenv dependency) and provides typed accessors
for LLM provider selection and API keys. Auto-imports env keys into
SecureStorage on startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from swiftagent.models.provider import (
    PROVIDER_KEY_ENV_VARS,
    ANTHROPIC_EXTRA_ENV_VARS,
    ProviderId,
)


def load_dotenv(dotenv_path: str | Path | None = None) -> None:
    """Load a .env file into os.environ (simple stdlib parser).

    Only sets variables that are NOT already in the environment,
    so real env vars always take precedence.
    """
    if dotenv_path is None:
        # Search: project root → cwd → home
        candidates = [
            Path(__file__).resolve().parents[2] / ".env",  # server/../.env
            Path.cwd() / ".env",
            Path.home() / ".env",
        ]
        for candidate in candidates:
            if candidate.is_file():
                dotenv_path = candidate
                break

    if dotenv_path is None:
        return

    path = Path(dotenv_path)
    if not path.is_file():
        return

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # Only set if not already in env (real env takes precedence)
            if key not in os.environ:
                os.environ[key] = value


def get_env_provider() -> tuple[str | None, str | None]:
    """Return (provider_id, model_id) from LLM_PROVIDER / LLM_MODEL env vars."""
    provider = os.environ.get("LLM_PROVIDER")
    model = os.environ.get("LLM_MODEL")
    return provider, model


def get_env_api_key(provider_id: ProviderId) -> str | None:
    """Get the API key for a provider from environment variables."""
    env_var = PROVIDER_KEY_ENV_VARS.get(provider_id)
    if env_var is None:
        return None
    return os.environ.get(env_var) or None


def get_env_anthropic_extras() -> dict[str, str | None]:
    """Get Anthropic extra env vars (auth_token, base_url)."""
    return {
        key: os.environ.get(env_var) or None
        for key, env_var in ANTHROPIC_EXTRA_ENV_VARS.items()
    }


def auto_import_env_keys(secure_storage) -> list[str]:
    """Import API keys from environment into SecureStorage if not already stored.

    Returns list of provider IDs whose keys were imported.
    """
    imported: list[str] = []

    for provider_id, env_var in PROVIDER_KEY_ENV_VARS.items():
        env_key = os.environ.get(env_var)
        if not env_key:
            continue
        # Only import if SecureStorage doesn't already have a key
        existing = secure_storage.get_api_key(provider_id.value)
        if not existing:
            secure_storage.store_api_key(provider_id.value, env_key)
            imported.append(provider_id.value)

    return imported


def get_configured_providers() -> list[dict]:
    """Return info about which providers have API keys configured (env or stored)."""
    results = []
    for provider_id in ProviderId:
        if provider_id == ProviderId.OLLAMA:
            results.append({
                "id": provider_id.value,
                "has_key": True,  # Ollama is local, always "configured"
                "source": "local",
            })
            continue

        env_var = PROVIDER_KEY_ENV_VARS.get(provider_id)
        env_key = os.environ.get(env_var, "") if env_var else ""
        results.append({
            "id": provider_id.value,
            "has_key": bool(env_key),
            "source": "env" if env_key else "none",
        })

    return results
