"""SwiftAgent CLI for agent-neutral onboarding and local server launch.

Usage:
    python -m swiftagent.cli onboard          # Configure local defaults
    python -m swiftagent.cli onboard --show   # Show free local detection
    python -m swiftagent.cli run              # Start server (default)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

AGENT_PROBES = (
    ("claude-code", "Claude Code", "SWIFTAGENT_CLAUDE_PATH", "claude"),
    ("codex", "Codex", "SWIFTAGENT_CODEX_PATH", "codex"),
    ("opencode", "OpenCode", "SWIFTAGENT_OPENCODE_PATH", "opencode"),
)
DEFAULT_AGENT_IDS = {agent_id for agent_id, *_ in AGENT_PROBES} | {
    "acp-agent",
    "generic-command",
}


def _env_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    return project_root / ".env"


def _read_env(path: Path) -> dict[str, str]:
    def strip_inline_comment(raw: str) -> str:
        in_single = False
        in_double = False
        escaped = False
        out: list[str] = []
        for char in raw:
            if escaped:
                out.append(char)
                escaped = False
                continue
            if char == "\\":
                out.append(char)
                escaped = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
                out.append(char)
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                out.append(char)
                continue
            if char == "#" and not in_single and not in_double:
                break
            out.append(char)
        value = "".join(out).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
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
        with open(example_path, encoding="utf-8") as example_file:
            for line in example_file:
                stripped = line.strip()
                if stripped and "=" in stripped and not stripped.startswith("#"):
                    key, _, _ = stripped.partition("=")
                    normalized_key = key.strip()
                    if normalized_key in values:
                        lines.append(f"{normalized_key}={values[normalized_key]}\n")
                    else:
                        lines.append(line)
                else:
                    lines.append(line)
        with open(path, "w", encoding="utf-8") as env_file:
            env_file.writelines(lines)
        return

    with open(path, "w", encoding="utf-8") as env_file:
        for key, value in values.items():
            env_file.write(f"{key}={value}\n")


def _resolve_executable(env_values: dict[str, str], env_key: str, command: str) -> str | None:
    configured = env_values.get(env_key, "").strip()
    return configured or shutil.which(command)


def _version(path: str | None) -> str:
    if not path:
        return "not found"
    try:
        process = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {exc}"
    if process.returncode != 0:
        return f"error: {(process.stderr or process.stdout).strip() or 'version check failed'}"
    return (process.stdout or process.stderr).strip()[:256] or "unknown"


def _detected_rows(env_values: dict[str, str]) -> list[tuple[str, str, str | None, str]]:
    rows: list[tuple[str, str, str | None, str]] = []
    for agent_id, label, env_key, command in AGENT_PROBES:
        executable = _resolve_executable(env_values, env_key, command)
        rows.append((agent_id, label, executable, _version(executable)))
    return rows


def _acp_summary(raw_command: str) -> str:
    if not raw_command.strip():
        return "not configured"
    try:
        command = json.loads(raw_command)
    except json.JSONDecodeError:
        return "invalid JSON; fix before use"
    if not isinstance(command, list) or not command or not all(
        isinstance(argument, str) and argument for argument in command
    ):
        return "invalid literal argument array"
    return f"configured ({len(command)} literal argument{'s' if len(command) != 1 else ''})"


def onboard_show() -> None:
    env_path = _env_path()
    env_values = _read_env(env_path)

    print("\n╔══════════════════════════════════════════╗")
    print("║       SwiftAgent — Local Agents          ║")
    print("╚══════════════════════════════════════════╝\n")
    print(f"  .env file: {env_path if env_path.is_file() else f'not found ({env_path})'}")
    print("\n  Free local detection (no model call):")
    for _agent_id, label, executable, version in _detected_rows(env_values):
        print(f"    {label:<12} {executable or 'not found'}")
        print(f"    {'':<12} {version}")
    print(f"    {'ACP v1':<12} {_acp_summary(env_values.get('SWIFTAGENT_ACP_COMMAND_JSON', ''))}")

    print("\n  Shared defaults:")
    print(
        "    SWIFTAGENT_DEFAULT_AGENT_ID: "
        f"{env_values.get('SWIFTAGENT_DEFAULT_AGENT_ID', 'first ready agent in the UI')}"
    )
    print(
        "    SWIFTAGENT_WORKSPACE_DIR: "
        f"{env_values.get('SWIFTAGENT_WORKSPACE_DIR', str(Path.home() / '.swiftagent' / 'workspace'))}"
    )
    print(f"    SWIFTAGENT_SANDBOX_MODE: {env_values.get('SWIFTAGENT_SANDBOX_MODE', 'strict')}")
    print("\n  Detection does not prove authentication or live compatibility.")
    print("  Open Your agents in the app for adapter-specific readiness and capabilities.\n")


def onboard_interactive() -> None:
    env_path = _env_path()
    env_values = _read_env(env_path)

    print("\n╔══════════════════════════════════════════╗")
    print("║       SwiftAgent — Local Onboarding      ║")
    print("╚══════════════════════════════════════════╝\n")
    print("  Detected executables (version checks only; no model call):")
    rows = _detected_rows(env_values)
    for _agent_id, label, executable, version in rows:
        print(f"    {label}: {executable or 'not found'} ({version})")

    for _agent_id, label, env_key, command in AGENT_PROBES:
        current = env_values.get(env_key, "").strip()
        detected = _resolve_executable(env_values, env_key, command) or "not found"
        custom = input(
            f"  {label} path override (Enter for {current or detected}): "
        ).strip()
        if custom:
            env_values[env_key] = custom

    current_acp = env_values.get("SWIFTAGENT_ACP_COMMAND_JSON", "")
    acp_command = input(
        "  ACP command as a literal JSON array (Enter to keep current/disabled): "
    ).strip()
    if acp_command:
        if _acp_summary(acp_command).startswith("configured"):
            env_values["SWIFTAGENT_ACP_COMMAND_JSON"] = acp_command
        else:
            print("  ! ACP command was invalid and was not saved.")
    elif current_acp:
        env_values["SWIFTAGENT_ACP_COMMAND_JSON"] = current_acp

    detected_default = next((row[0] for row in rows if row[2]), "claude-code")
    default_agent = env_values.get("SWIFTAGENT_DEFAULT_AGENT_ID", detected_default)
    requested_default = input(f"  Default agent id (default: {default_agent}): ").strip()
    chosen_default = requested_default or default_agent
    if chosen_default not in DEFAULT_AGENT_IDS:
        print(f"  ! Unknown built-in agent id '{chosen_default}'; keeping {default_agent}.")
        chosen_default = default_agent
    env_values["SWIFTAGENT_DEFAULT_AGENT_ID"] = chosen_default

    workspace_default = env_values.get(
        "SWIFTAGENT_WORKSPACE_DIR", str(Path.home() / ".swiftagent" / "workspace")
    )
    workspace = input(f"  Workspace dir (default: {workspace_default}): ").strip()
    env_values["SWIFTAGENT_WORKSPACE_DIR"] = workspace or workspace_default

    sandbox_default = env_values.get("SWIFTAGENT_SANDBOX_MODE", "strict")
    sandbox = input(
        f"  Isolation [strict/fallback] (default: {sandbox_default}): "
    ).strip().lower()
    env_values["SWIFTAGENT_SANDBOX_MODE"] = (
        sandbox if sandbox in {"strict", "fallback"} else sandbox_default
    )

    _write_env(env_path, env_values)

    print(f"\n  ✓ Configuration saved to {env_path}")
    print("\n  Next steps:")
    print("    1. make dev")
    print("    2. Open Your agents and refresh local detection")
    print("    3. Review adapter capabilities and safety before a sensitive run\n")


def main() -> None:
    arguments = sys.argv[1:]

    if not arguments or arguments[0] == "run":
        from swiftagent.main import main as server_main

        server_main()
        return

    if arguments[0] == "onboard":
        if "--show" in arguments:
            onboard_show()
        else:
            onboard_interactive()
        return

    if arguments[0] in {"--help", "-h"}:
        print("SwiftAgent CLI\n")
        print("  python -m swiftagent.cli run              Start the local server")
        print("  python -m swiftagent.cli onboard          Configure local agent defaults")
        print("  python -m swiftagent.cli onboard --show   Show free local agent detection")
        return

    print(f"Unknown command: {arguments[0]}")
    print("Run 'python -m swiftagent.cli --help' for usage")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
