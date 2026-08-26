"""Read-only status for a user-configured ACP v1 agent command."""

from __future__ import annotations

import shutil
from pathlib import Path

from swiftagent.agents.acp import settings as acp_settings
from swiftagent.models.agent import AgentDefinition, AgentStatus


def _resolve_executable(executable: str) -> str | None:
    candidate = Path(executable).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(executable)


def get_status(definition: AgentDefinition) -> AgentStatus:
    try:
        command = acp_settings.get_command()
    except ValueError as exc:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            auth_status="error",
            detail=str(exc),
        )
    if not command:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            detail=(
                "Configure SWIFTAGENT_ACP_COMMAND_JSON with a literal argv array, for example "
                '["my-agent", "acp"].'
            ),
        )
    executable = _resolve_executable(command[0])
    if not executable:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            detail=f"Configured ACP executable was not found: {command[0]}",
        )
    return AgentStatus(
        **definition.model_dump(),
        installed=True,
        executable_path=executable,
        compatible=None,
        auth_status="unknown",
        detail="Configured for ACP v1. Capabilities are negotiated when a session starts.",
    )
