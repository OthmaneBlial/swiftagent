"""Manifest, executable, and disposable-test readiness for generic commands."""

from __future__ import annotations

from swiftagent.agents.generic_command import settings as generic_settings
from swiftagent.agents.generic_command.manifest import (
    executable_identity,
    fingerprint,
    resolve_executable,
)
from swiftagent.models.agent import AgentDefinition, AgentStatus


def get_status(definition: AgentDefinition) -> AgentStatus:
    try:
        manifest = generic_settings.get_manifest()
    except ValueError as exc:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            auth_status="error",
            detail=str(exc),
        )
    if manifest is None:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            detail="Save a reviewed generic-command manifest, then run its disposable test.",
        )
    executable = resolve_executable(manifest)
    if not executable:
        return AgentStatus(
            **definition.model_dump(),
            installed=False,
            compatible=False,
            detail=f"Configured executable was not found: {manifest.executable}",
        )
    receipt = generic_settings.get_receipt()
    if receipt is None:
        return AgentStatus(
            **definition.model_dump(),
            installed=True,
            executable_path=executable,
            compatible=False,
            detail="Manifest saved but disabled until the disposable adapter test passes.",
        )
    try:
        identity_matches = receipt.executable_identity == executable_identity(executable)
    except OSError:
        identity_matches = False
    manifest_matches = receipt.manifest_fingerprint == fingerprint(manifest)
    if not identity_matches or not manifest_matches:
        return AgentStatus(
            **definition.model_dump(),
            installed=True,
            executable_path=executable,
            compatible=False,
            detail="Manifest or executable changed after testing. Run the disposable test again.",
        )
    return AgentStatus(
        **definition.model_dump(),
        installed=True,
        executable_path=executable,
        version=receipt.version_output,
        compatible=True,
        detail=(
            f"Text-only adapter verified in a disposable workspace at "
            f"{receipt.tested_at.isoformat()}."
        ),
    )
