"""Read-only discovery and compatibility status for Claude Code."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime

from swiftagent.agents.claude import settings as claude_settings
from swiftagent.models.agent import AgentDefinition, AgentStatus
from swiftagent.storage import settings as settings_repo
from swiftagent.tools.sandbox import check_bwrap_usable
from swiftagent.tools.workspace import get_workspace_dir

AUTH_PROBE_CACHE: dict[str, str | None] = {
    "status": "not_checked",
    "message": None,
    "checked_at": None,
}


def resolve_cli_path() -> str | None:
    configured = claude_settings.get_cli_path()
    return configured or shutil.which("claude")


def get_status(definition: AgentDefinition) -> AgentStatus:
    """Probe installation/version locally without making a model request."""
    executable = resolve_cli_path()
    if not executable:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            auth_status="not_checked",
            detail="Claude Code was not found on PATH. Install it, then refresh.",
        )

    version = None
    compatible: bool | None = None
    detail = "Detected. Authentication is checked by Claude Code when a run starts."
    try:
        proc = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        raw_version = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode == 0 and raw_version:
            version = raw_version[:256]
            compatible = None
            detail = (
                "Detected locally. This version has not yet passed SwiftAgent's published live "
                "compatibility matrix."
            )
        else:
            version = None
            compatible = False
            detail = "The Claude executable was found but its version check failed."
    except (OSError, subprocess.SubprocessError) as exc:
        compatible = False
        detail = f"The Claude executable could not be inspected: {exc}"

    return AgentStatus(
        **definition.model_dump(),
        installed=True,
        executable_path=executable,
        version=version,
        compatible=compatible,
        auth_status="unknown",
        detail=detail,
    )


def probe_auth(claude_path: str | None, model: str | None) -> tuple[str, str | None]:
    """Compatibility probe retained for the legacy endpoint.

    The agent-aware status endpoint uses a free, local CLI status command instead.
    """
    if not claude_path:
        return "unavailable", "Claude CLI not found"

    args = [claude_path, "-p", "--output-format", "json"]
    if model:
        args.extend(["--model", model])
    args.append("Reply with exactly: OK")

    try:
        proc = subprocess.run(
            args,
            cwd=str(get_workspace_dir()),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return "error", str(exc)

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return "error", (proc.stderr or "Auth probe produced no output").strip() or "unknown"

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return "error", "Auth probe returned non-JSON output"

    if payload.get("is_error"):
        return "error", str(payload.get("result") or "Claude auth probe failed")
    return "ok", None


def get_legacy_engine_status(*, probe_authentication: bool = False) -> dict:
    """Build the historical `/engine/status` response without leaking into API core."""
    claude_path = resolve_cli_path()
    bwrap_available = shutil.which("bwrap") is not None
    sandbox_mode = settings_repo.get_sandbox_mode()
    workspace = get_workspace_dir()

    bwrap_usable = False
    bwrap_reason = None
    if bwrap_available:
        bwrap_usable, bwrap_reason = check_bwrap_usable(workspace)

    strict_active = sandbox_mode == "strict" and bwrap_usable
    degraded = sandbox_mode == "strict" and not strict_active
    degraded_reason = None
    if degraded:
        if not bwrap_available:
            degraded_reason = (
                "Strict mode is blocked: bwrap is missing. Install bwrap or explicitly select "
                "fallback mode."
            )
        else:
            degraded_reason = (
                "Strict mode is blocked: bwrap is unusable. Repair bwrap or explicitly select "
                "fallback mode."
            )
            if bwrap_reason:
                degraded_reason = f"{degraded_reason} ({bwrap_reason})"

    if probe_authentication:
        status, message = probe_auth(claude_path, claude_settings.get_model())
        AUTH_PROBE_CACHE["status"] = status
        AUTH_PROBE_CACHE["message"] = message
        AUTH_PROBE_CACHE["checked_at"] = datetime.now(UTC).isoformat()

    return {
        "claude_cli_available": claude_path is not None,
        "claude_cli_path": claude_path,
        "bwrap_available": bwrap_available,
        "bwrap_usable": bwrap_usable,
        "bwrap_reason": bwrap_reason,
        "workspace_dir": settings_repo.get_workspace_dir(),
        "sandbox_mode": sandbox_mode,
        "strict_sandbox_active": strict_active,
        "degraded": degraded,
        "degraded_reason": degraded_reason,
        "auth_probe": AUTH_PROBE_CACHE,
    }
