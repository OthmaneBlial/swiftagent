"""Free, read-only discovery for the built-in OpenCode integration."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.models.agent import (
    AgentCapabilities,
    AgentDefinition,
    AgentModelOption,
    AgentStatus,
)
from swiftagent.storage import settings as settings_repo

TESTED_VERSION = (1, 18, 13)
MINIMUM_VERSION = (1, 18, 0)
_VERSION = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")
_MODEL_ID = re.compile(r"^[A-Za-z0-9_.-]+/[^\s/][^\s]*$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
Transport = Literal["acp", "json", "unsupported"]


def resolve_cli_path() -> str | None:
    configured = opencode_settings.get_cli_path()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return str(candidate.resolve()) if candidate.is_file() else None
        return shutil.which(configured)
    return shutil.which("opencode")


def _run(
    executable: str,
    *args: str,
    timeout: int = 5,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(cwd) if cwd else None,
    )


def detect_transport(executable: str) -> Transport:
    try:
        acp = _run(executable, "acp", "--help", timeout=3)
        acp_help = f"{acp.stdout}\n{acp.stderr}".lower()
        if acp.returncode == 0 and "agent client protocol" in acp_help:
            return "acp"

        run = _run(executable, "run", "--help", timeout=3)
        run_help = f"{run.stdout}\n{run.stderr}".lower()
        if run.returncode == 0 and "--format" in run_help and "json" in run_help:
            return "json"
    except (OSError, subprocess.SubprocessError):
        return "unsupported"
    return "unsupported"


def discover_models(executable: str) -> list[AgentModelOption]:
    """Read OpenCode's own current provider/model catalog without an inference call."""
    configured_workspace = Path(settings_repo.get_workspace_dir()).expanduser().resolve()
    probe_cwd = configured_workspace if configured_workspace.is_dir() else None
    try:
        result = _run(executable, "models", timeout=10, cwd=probe_cwd)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    models: list[AgentModelOption] = []
    seen: set[str] = set()
    for raw_line in result.stdout.splitlines():
        model_id = _ANSI.sub("", raw_line).strip()
        if not _MODEL_ID.fullmatch(model_id) or model_id in seen:
            continue
        seen.add(model_id)
        provider = model_id.split("/", 1)[0]
        models.append(AgentModelOption(id=model_id, name=model_id, provider=provider))
        if len(models) >= 256:
            break
    return models


def _fallback_capabilities(definition: AgentDefinition) -> AgentCapabilities:
    return definition.capabilities.model_copy(
        update={
            "approvals": False,
            "questions": False,
            "plan_updates": False,
            "native_sandbox": False,
        }
    )


def get_status(definition: AgentDefinition) -> AgentStatus:
    executable = resolve_cli_path()
    if not executable:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            detail="OpenCode was not found. Install it, then refresh local detection.",
        )

    version: str | None = None
    parsed: tuple[int, int, int] | None = None
    try:
        version_result = _run(executable, "--version", timeout=3)
        raw_version = (version_result.stdout or version_result.stderr or "").strip()
        match = _VERSION.search(raw_version) if version_result.returncode == 0 else None
        if match:
            version = raw_version[:256]
            parsed = tuple(int(part) for part in match.groups())
    except (OSError, subprocess.SubprocessError):
        pass

    transport = detect_transport(executable)
    models = discover_models(executable) if transport != "unsupported" else []
    capabilities = (
        definition.capabilities if transport == "acp" else _fallback_capabilities(definition)
    )

    compatible: bool | None
    if not parsed or parsed < MINIMUM_VERSION or transport == "unsupported":
        compatible = False
    elif parsed == TESTED_VERSION:
        compatible = True
    else:
        compatible = None

    if transport == "acp":
        detail = (
            "OpenCode ACP v1 is verified for this exact CLI version."
            if compatible is True
            else "OpenCode exposes ACP v1; this version is not in the verified matrix yet."
        )
    elif transport == "json":
        detail = (
            "ACP is unavailable. SwiftAgent will use reduced JSON-run mode: no interactive "
            "approvals, questions, plans, or native sandbox controls."
        )
    elif parsed and parsed < MINIMUM_VERSION:
        detail = "This OpenCode version predates SwiftAgent's tested integration contract."
    else:
        detail = "This OpenCode installation exposes neither ACP nor JSON-run integration."

    auth_status = "ready" if models else "action_required"
    if not models and transport != "unsupported":
        detail = f"{detail} Run `opencode auth login` or configure an available provider/model."

    payload = definition.model_dump()
    payload["capabilities"] = capabilities
    payload["protocol"] = "acp-v1" if transport == "acp" else "opencode-json-run"
    return AgentStatus(
        **payload,
        installed=True,
        executable_path=executable,
        version=version,
        compatible=compatible,
        auth_status=auth_status,
        detail=detail,
        models=models,
    )
