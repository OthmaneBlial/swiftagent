"""
SwiftAgent CLI — onboard command & server launcher.

Usage:
    python -m swiftagent.cli onboard          # Interactive setup wizard
    python -m swiftagent.cli onboard --show   # Show current config status
    python -m swiftagent.cli run              # Start the server (default)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from swiftagent.models.provider import (
    DEFAULT_MODELS,
    PROVIDER_KEY_ENV_VARS,
    PROVIDER_LABELS,
    ProviderId,
)


# ═══════════════════════════════════════════════════════════════
# Onboard
# ═══════════════════════════════════════════════════════════════

def _env_path() -> Path:
    """Find or create .env in the project root."""
    # Try project root (two levels up from server/swiftagent/cli.py)
    project_root = Path(__file__).resolve().parents[2]
    return project_root / ".env"


def _read_env(path: Path) -> dict[str, str]:
    """Parse an existing .env file into a dict."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    """Write a .env file preserving comments from .env.example if available."""
    example_path = path.parent / ".env.example"

    if example_path.is_file():
        # Use .env.example as template, fill in values
        lines: list[str] = []
        with open(example_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped and "=" in stripped and not stripped.startswith("#"):
                    key, _, _ = stripped.partition("=")
                    key = key.strip()
                    if key in values:
                        lines.append(f"{key}={values[key]}\n")
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
        with open(path, "w") as f:
            f.writelines(lines)
    else:
        # Write plain key=value
        with open(path, "w") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")


def onboard_show() -> None:
    """Show current provider configuration status."""
    env_path = _env_path()
    env_values = _read_env(env_path)

    print("\n╔══════════════════════════════════════════╗")
    print("║        SwiftAgent — Config Status        ║")
    print("╚══════════════════════════════════════════╝\n")

    # Show .env file location
    if env_path.is_file():
        print(f"  .env file: {env_path}")
    else:
        print(f"  .env file: not found (expected at {env_path})")

    # Show active provider
    provider = env_values.get("LLM_PROVIDER", "(not set)")
    model = env_values.get("LLM_MODEL", "(not set)")
    print(f"\n  Active Provider: {provider}")
    print(f"  Active Model:    {model}\n")

    # Show all providers and their key status
    print("  ┌──────────────┬──────────────────────┬──────────┐")
    print("  │ Provider     │ Env Var              │ Status   │")
    print("  ├──────────────┼──────────────────────┼──────────┤")
    for pid in ProviderId:
        if pid == ProviderId.OLLAMA:
            print(f"  │ {'ollama':<12} │ {'(local)':<20} │ {'✓ local':<8} │")
            continue
        env_var = PROVIDER_KEY_ENV_VARS.get(pid, "")
        env_key = env_values.get(env_var, "") or os.environ.get(env_var, "")
        status = "✓ ready" if env_key else "✗ empty"
        print(f"  │ {pid.value:<12} │ {env_var:<20} │ {status:<8} │")
    print("  └──────────────┴──────────────────────┴──────────┘")
    print()


def onboard_interactive() -> None:
    """Interactive onboard wizard."""
    env_path = _env_path()
    env_values = _read_env(env_path)

    print("\n╔══════════════════════════════════════════╗")
    print("║       SwiftAgent — Onboard Wizard        ║")
    print("╚══════════════════════════════════════════╝\n")

    # 1. Select provider
    providers_with_keys = [p for p in ProviderId if p != ProviderId.OLLAMA]
    print("  Available LLM Providers:\n")
    for i, pid in enumerate(providers_with_keys, 1):
        label = PROVIDER_LABELS.get(pid, pid.value)
        models = DEFAULT_MODELS.get(pid, [])
        model_names = ", ".join(m.display_name for m in models[:2])
        print(f"    {i}. {label:<25} ({model_names})")
    print(f"    {len(providers_with_keys) + 1}. Ollama (Local)           (no API key needed)")
    print()

    while True:
        choice = input("  Select provider [1-7]: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(providers_with_keys):
                selected = providers_with_keys[idx - 1]
                break
            elif idx == len(providers_with_keys) + 1:
                selected = ProviderId.OLLAMA
                break
        except ValueError:
            pass
        print("  Invalid choice, try again.")

    print(f"\n  → Selected: {PROVIDER_LABELS.get(selected, selected.value)}\n")
    env_values["LLM_PROVIDER"] = selected.value

    # 2. API Key (if not Ollama)
    if selected != ProviderId.OLLAMA:
        env_var = PROVIDER_KEY_ENV_VARS[selected]
        existing = env_values.get(env_var, "") or os.environ.get(env_var, "")

        if existing:
            masked = existing[:8] + "…" + existing[-4:]
            print(f"  Existing key found: {masked}")
            keep = input("  Keep existing key? [Y/n]: ").strip().lower()
            if keep in ("n", "no"):
                existing = ""

        if not existing:
            api_key = input(f"  Enter {env_var}: ").strip()
            if api_key:
                env_values[env_var] = api_key
            else:
                print("  ⚠  No key provided. You can add it later in .env")

        # Anthropic extras
        if selected == ProviderId.ANTHROPIC:
            auth_token = input("  ANTHROPIC_AUTH_TOKEN (optional, press Enter to skip): ").strip()
            if auth_token:
                env_values["ANTHROPIC_AUTH_TOKEN"] = auth_token
            base_url = input("  ANTHROPIC_BASE_URL (optional, press Enter for default): ").strip()
            if base_url:
                env_values["ANTHROPIC_BASE_URL"] = base_url

    # 3. Select model
    models = DEFAULT_MODELS.get(selected, [])
    if models:
        print(f"\n  Available models for {PROVIDER_LABELS.get(selected, selected.value)}:\n")
        for i, m in enumerate(models, 1):
            ctx = f"{(m.context_window or 0) // 1000}K ctx" if m.context_window else ""
            print(f"    {i}. {m.display_name:<25} {ctx}")
        print(f"    {len(models) + 1}. latest (auto-select)\n")

        model_choice = input(f"  Select model [1-{len(models) + 1}]: ").strip()
        try:
            midx = int(model_choice)
            if 1 <= midx <= len(models):
                env_values["LLM_MODEL"] = models[midx - 1].id
            else:
                env_values["LLM_MODEL"] = "latest"
        except ValueError:
            env_values["LLM_MODEL"] = "latest"

        print(f"  → Model: {env_values.get('LLM_MODEL', 'latest')}")
    else:
        env_values["LLM_MODEL"] = "latest"

    # 4. Write .env
    _write_env(env_path, env_values)
    print(f"\n  ✓ Configuration saved to {env_path}")

    # 5. Summary
    print("\n  ┌─ Setup Complete! ────────────────────────┐")
    print(f"  │ Provider: {PROVIDER_LABELS.get(selected, selected.value):<30}│")
    print(f"  │ Model:    {env_values.get('LLM_MODEL', 'latest'):<30}│")
    print("  │                                          │")
    print("  │ Start SwiftAgent:                        │")
    print("  │   make dev                               │")
    print("  │                                          │")
    print("  │ Or just the server:                      │")
    print("  │   make dev-server                        │")
    print("  └──────────────────────────────────────────┘\n")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] == "run":
        # Just launch the server
        from swiftagent.main import main as server_main
        server_main()
    elif args[0] == "onboard":
        if "--show" in args:
            onboard_show()
        else:
            onboard_interactive()
    elif args[0] == "--help" or args[0] == "-h":
        print("SwiftAgent CLI")
        print()
        print("  python -m swiftagent.cli run              Start the server")
        print("  python -m swiftagent.cli onboard          Interactive setup wizard")
        print("  python -m swiftagent.cli onboard --show   Show current config status")
    else:
        print(f"Unknown command: {args[0]}")
        print("Run 'python -m swiftagent.cli --help' for usage")
        sys.exit(1)


if __name__ == "__main__":
    main()
