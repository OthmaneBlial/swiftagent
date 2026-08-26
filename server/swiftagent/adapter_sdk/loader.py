"""Discover and register reviewed local adapter manifests."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from swiftagent.adapter_sdk.manifest import AdapterManifest, load_manifest, resolve_command
from swiftagent.agents.acp import AcpAdapter
from swiftagent.agents.registry import AgentRegistry
from swiftagent.models.agent import AgentDefinition, AgentStatus

BASE_ENVIRONMENT = ("HOME", "LANG", "LC_ALL", "PATH", "TMPDIR")
MAX_ADAPTER_MANIFESTS = 64
MAX_LOAD_ERROR_CHARS = 512
LOAD_ERRORS: list[str] = []


def adapter_directory(data_dir: Path) -> Path:
    configured = os.environ.get("SWIFTAGENT_ADAPTER_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else data_dir / "adapters"


def _environment_for(manifest: AdapterManifest) -> dict[str, str]:
    allowed = set(BASE_ENVIRONMENT) | set(manifest.environment_allowlist)
    return {name: os.environ[name] for name in sorted(allowed) if name in os.environ}


def _resolve_executable(command: list[str]) -> str | None:
    candidate = Path(command[0]).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(command[0])


def _status_provider(
    manifest: AdapterManifest,
    manifest_path: Path,
):
    command = resolve_command(manifest, manifest_path)

    def provide(definition: AgentDefinition) -> AgentStatus:
        executable = _resolve_executable(command)
        if not executable:
            return AgentStatus(
                **definition.model_dump(),
                installed=False,
                compatible=False,
                detail=f"Local adapter executable was not found: {command[0]}",
            )

        version: str | None = None
        detail = (
            "Loaded from a local manifest. Capabilities are negotiated at run time; "
            "SwiftAgent does not endorse or auto-update this command."
        )
        if manifest.version_probe:
            try:
                result = subprocess.run(
                    [*command, *manifest.version_probe.arguments],
                    capture_output=True,
                    text=True,
                    timeout=manifest.version_probe.timeout_seconds,
                    check=False,
                    env=_environment_for(manifest),
                )
                raw = (result.stdout or result.stderr).strip()
                match = re.search(manifest.version_probe.regex, raw) if result.returncode == 0 else None
                if match:
                    version = (match.group(1) if match.groups() else match.group(0))[:256]
                else:
                    detail = f"{detail} Its configured version probe did not match."
            except (OSError, subprocess.SubprocessError) as exc:
                detail = f"{detail} Version probe failed: {exc}"

        if manifest.compatibility:
            detail = (
                f"{detail} Manifest declares {manifest.compatibility.contract_suite} passed on "
                f"{manifest.compatibility.tested_at}; review its evidence before use."
            )
        return AgentStatus(
            **definition.model_dump(),
            installed=True,
            executable_path=executable,
            version=version,
            compatible=None,
            auth_status="unknown",
            detail=detail,
        )

    return provide


def register_manifest(
    registry: AgentRegistry,
    manifest: AdapterManifest,
    manifest_path: Path,
) -> None:
    command = resolve_command(manifest, manifest_path)
    environment = _environment_for(manifest)
    definition = AgentDefinition(
        agent_id=manifest.agent_id,
        display_name=manifest.display_name,
        adapter_id=manifest.adapter_id,
        adapter_version=manifest.adapter_version,
        protocol=manifest.protocol,
        trust_level="local_custom",
        trust_evidence=None,
        install_url=manifest.install_url,
        documentation_url=manifest.documentation_url,
        capabilities=manifest.capabilities,
    )

    def factory(task, manager):
        return AcpAdapter(task, manager, command=command, environment=environment)

    registry.register(definition, factory, _status_provider(manifest, manifest_path))


def _bounded_load_error(manifest_path: Path, error: Exception) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    summary = " · ".join(lines[:2]) if lines else error.__class__.__name__
    message = f"{manifest_path.name}: {summary}"
    if len(message) <= MAX_LOAD_ERROR_CHARS:
        return message
    return f"{message[: MAX_LOAD_ERROR_CHARS - 1].rstrip()}…"


def load_external_adapters(registry: AgentRegistry, data_dir: Path) -> list[str]:
    """Load direct JSON children only; one broken manifest cannot block startup."""
    global LOAD_ERRORS
    LOAD_ERRORS = []
    directory = adapter_directory(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    candidates = sorted(directory.glob("*.adapter.json"))
    if len(candidates) > MAX_ADAPTER_MANIFESTS:
        LOAD_ERRORS.append(
            f"Adapter directory has {len(candidates)} manifests; only {MAX_ADAPTER_MANIFESTS} are allowed"
        )
        candidates = candidates[:MAX_ADAPTER_MANIFESTS]

    for manifest_path in candidates:
        try:
            manifest = load_manifest(manifest_path)
            register_manifest(registry, manifest, manifest_path)
        except (OSError, RuntimeError, ValueError) as exc:
            LOAD_ERRORS.append(_bounded_load_error(manifest_path, exc))
    return list(LOAD_ERRORS)


def load_errors() -> list[str]:
    return list(LOAD_ERRORS)
