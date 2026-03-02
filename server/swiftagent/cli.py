"""
SwiftAgent CLI — onboarding and server launcher.

Usage:
    python -m swiftagent.cli onboard          # Interactive Claude setup
    python -m swiftagent.cli onboard --show   # Show current config status
    python -m swiftagent.cli run              # Start server (default)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _env_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / ".env"


def _read_env(path: Path) -> dict[str, str]:
    def strip_inline_comment(raw: str) -> str:
        in_single = False
        in_double = False
        escaped = False
        out: list[str] = []
        for ch in raw:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == "'" and not in_double:
                in_single = not in_single
                out.append(ch)
                continue
            if ch == '"' and not in_single:
                in_double = not in_double
                out.append(ch)
                continue
            if ch == "#" and not in_single and not in_double:
                break
            out.append(ch)
        value = "".join(out).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = strip_inline_comment(value)
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    example_path = path.parent / ".env.example"

    if example_path.is_file():
        lines: list[str] = []
        with open(example_path, encoding="utf-8") as f:
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
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        with open(path, "w", encoding="utf-8") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")


def _resolve_claude_path(env_values: dict[str, str]) -> str | None:
    configured = env_values.get("SWIFTAGENT_CLAUDE_PATH", "").strip()
    if configured:
        return configured
    return shutil.which("claude")


def _claude_version(path: str | None) -> str:
    if not path:
        return "not found"
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as e:  # pragma: no cover - defensive
        return f"error: {e}"
    if proc.returncode != 0:
        return f"error: {(proc.stderr or proc.stdout).strip() or 'unknown'}"
    return (proc.stdout or "").strip() or "unknown"


def onboard_show() -> None:
    env_path = _env_path()
    env_values = _read_env(env_path)

    claude_path = _resolve_claude_path(env_values)
    claude_version = _claude_version(claude_path)
    bwrap_path = shutil.which("bwrap")

    print("\n╔══════════════════════════════════════════╗")
    print("║       SwiftAgent — Claude Status         ║")
    print("╚══════════════════════════════════════════╝\n")

    print(f"  .env file: {env_path if env_path.is_file() else f'not found ({env_path})'}")
    print(f"  Claude CLI path: {claude_path or 'not found'}")
    print(f"  Claude CLI version: {claude_version}")
    print(f"  bwrap: {bwrap_path or 'not found'}")

    print("\n  Current configuration:")
    print(f"    CLAUDE_MODEL: {env_values.get('CLAUDE_MODEL', '(default)')}")
    print(f"    CLAUDE_PERMISSION_MODE: {env_values.get('CLAUDE_PERMISSION_MODE', 'default')}")
    print(
        "    SWIFTAGENT_WORKSPACE_DIR: "
        f"{env_values.get('SWIFTAGENT_WORKSPACE_DIR', str(Path.home() / '.swiftagent' / 'workspace'))}"
    )
    print(f"    SWIFTAGENT_SANDBOX_MODE: {env_values.get('SWIFTAGENT_SANDBOX_MODE', 'strict')}")
    print()


def onboard_interactive() -> None:
    env_path = _env_path()
    env_values = _read_env(env_path)

    print("\n╔══════════════════════════════════════════╗")
    print("║      SwiftAgent — Claude Onboarding      ║")
    print("╚══════════════════════════════════════════╝\n")

    current_path = _resolve_claude_path(env_values)
    print(f"  Detected Claude CLI: {current_path or 'not found'}")
    custom_path = input("  Claude CLI path (Enter to keep detected): ").strip()
    if custom_path:
        env_values["SWIFTAGENT_CLAUDE_PATH"] = custom_path

    current_model = env_values.get("CLAUDE_MODEL", "")
    model = input(
        f"  Claude model alias/id (Enter for CLI default{f', current: {current_model}' if current_model else ''}): "
    ).strip()
    env_values["CLAUDE_MODEL"] = model

    permission_default = env_values.get("CLAUDE_PERMISSION_MODE", "default")
    permission = input(
        f"  Claude permission mode [default/acceptEdits/dontAsk/bypassPermissions/plan] (default: {permission_default}): "
    ).strip()
    env_values["CLAUDE_PERMISSION_MODE"] = permission or permission_default

    workspace_default = env_values.get(
        "SWIFTAGENT_WORKSPACE_DIR", str(Path.home() / ".swiftagent" / "workspace")
    )
    workspace = input(f"  Workspace dir (default: {workspace_default}): ").strip()
    env_values["SWIFTAGENT_WORKSPACE_DIR"] = workspace or workspace_default

    sandbox_default = env_values.get("SWIFTAGENT_SANDBOX_MODE", "strict")
    sandbox = input(f"  Sandbox mode [strict/fallback] (default: {sandbox_default}): ").strip().lower()
    env_values["SWIFTAGENT_SANDBOX_MODE"] = sandbox if sandbox in {"strict", "fallback"} else sandbox_default

    _write_env(env_path, env_values)

    print(f"\n  ✓ Configuration saved to {env_path}")
    print("\n  Next steps:")
    print("    1. make dev")
    print("    2. Open Settings in the app and verify engine status")
    print()


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] == "run":
        from swiftagent.main import main as server_main

        server_main()
        return

    if args[0] == "onboard":
        if "--show" in args:
            onboard_show()
        else:
            onboard_interactive()
        return

    if args[0] in {"--help", "-h"}:
        print("SwiftAgent CLI")
        print()
        print("  python -m swiftagent.cli run              Start the server")
        print("  python -m swiftagent.cli onboard          Interactive Claude setup")
        print("  python -m swiftagent.cli onboard --show   Show current Claude config")
        return

    print(f"Unknown command: {args[0]}")
    print("Run 'python -m swiftagent.cli --help' for usage")
    sys.exit(1)


if __name__ == "__main__":
    main()
