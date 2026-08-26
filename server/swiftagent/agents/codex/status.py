"""Local, free readiness probe for the Codex CLI and its official auth state."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from swiftagent.agents.codex import settings as codex_settings
from swiftagent.models.agent import AgentDefinition, AgentStatus

TESTED_VERSION = (0, 149, 1)
MINIMUM_VERSION = (0, 149, 0)
_VERSION = re.compile(r"(?:codex-cli\s+)?(\d+)\.(\d+)\.(\d+)")


def resolve_cli_path() -> str | None:
    configured = codex_settings.get_cli_path()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return str(candidate.resolve()) if candidate.is_file() else None
        return shutil.which(configured)
    return shutil.which("codex")


def _run(executable: str, *args: str, timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def get_status(definition: AgentDefinition) -> AgentStatus:
    executable = resolve_cli_path()
    if not executable:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            auth_status="not_checked",
            detail="Codex CLI was not found. Install Codex, then refresh local detection.",
        )

    version = None
    compatible: bool | None = False
    detail = "Codex was found, but its app-server compatibility could not be verified."
    auth_status = "unknown"
    try:
        version_result = _run(executable, "--version", timeout=3)
        raw_version = (version_result.stdout or version_result.stderr or "").strip()
        match = _VERSION.search(raw_version) if version_result.returncode == 0 else None
        if match:
            parsed = tuple(int(part) for part in match.groups())
            version = raw_version[:256]
            if parsed < MINIMUM_VERSION:
                detail = "This Codex version predates SwiftAgent's tested app-server v2 contract."
            elif parsed == TESTED_VERSION:
                compatible = True
                detail = "Codex app-server v2 contract is verified for this exact CLI version."
            else:
                compatible = None
                detail = "Codex app-server is available; this newer version is not in the live matrix yet."

            if parsed >= MINIMUM_VERSION:
                app_server_result = _run(executable, "app-server", "--help", timeout=3)
                if app_server_result.returncode != 0:
                    compatible = False
                    detail = "This Codex installation does not expose the required app-server command."

        auth_result = _run(executable, "login", "status")
        if auth_result.returncode == 0:
            auth_status = "ready"
        else:
            auth_status = "action_required"
            detail = f"{detail} Run `codex login` before starting a Codex task."
    except (OSError, subprocess.SubprocessError) as exc:
        detail = f"Codex could not be inspected safely: {exc}"
        compatible = False
        auth_status = "error"

    return AgentStatus(
        **definition.model_dump(),
        installed=True,
        executable_path=executable,
        version=version,
        compatible=compatible,
        auth_status=auth_status,
        detail=detail,
    )
