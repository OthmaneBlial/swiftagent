"""Validated manifest contract for out-of-process local adapters."""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from swiftagent.adapter_sdk import ADAPTER_API_VERSION, CONTRACT_SUITE_ID
from swiftagent.models.agent import AgentCapabilities

MAX_MANIFEST_BYTES = 256 * 1024
MAX_COMMAND_ARGUMENTS = 64
MAX_ARGUMENT_CHARS = 4_096
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_SHELL_EXECUTABLES = {
    "bash",
    "cmd",
    "cmd.exe",
    "fish",
    "powershell",
    "pwsh",
    "sh",
    "zsh",
}


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VersionProbe(ManifestModel):
    """Free local command used only to display an installed agent version."""

    arguments: list[str] = Field(default_factory=lambda: ["--version"], max_length=16)
    regex: str = Field(min_length=1, max_length=512)
    timeout_seconds: int = Field(default=5, ge=1, le=15)

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, arguments: list[str]) -> list[str]:
        if any(not argument or len(argument) > MAX_ARGUMENT_CHARS for argument in arguments):
            raise ValueError("Version-probe arguments must be non-empty bounded strings")
        return arguments

    @field_validator("regex")
    @classmethod
    def validate_regex(cls, pattern: str) -> str:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid version-probe regex: {exc}") from exc
        return pattern


class CompatibilityDeclaration(ManifestModel):
    """Contributor-supplied test scope; endorsement is assigned separately."""

    contract_suite: Literal[CONTRACT_SUITE_ID] = CONTRACT_SUITE_ID
    contract_result: Literal["passed"]
    tested_agent_versions: list[str] = Field(min_length=1, max_length=32)
    operating_systems: list[str] = Field(min_length=1, max_length=16)
    evidence: list[str] = Field(min_length=1, max_length=16)
    tested_at: date

    @field_validator("tested_agent_versions", "operating_systems", "evidence")
    @classmethod
    def validate_bounded_rows(cls, rows: list[str]) -> list[str]:
        normalized = [row.strip() for row in rows]
        if any(not row or len(row) > 512 for row in normalized):
            raise ValueError("Compatibility declaration rows must be non-empty and bounded")
        return normalized


class ContractFixture(ManifestModel):
    """Optional deterministic hooks used by the public contract harness."""

    prompt: str = Field(default="Exercise the adapter contract without network access.", max_length=4_096)
    fixture_files: dict[str, str] = Field(
        default_factory=lambda: {"fixture-input.txt": "safe adapter contract input\n"},
        max_length=16,
    )
    expected_event_types: list[str] = Field(default_factory=list, max_length=32)
    cancellation_arguments: list[str] = Field(default_factory=list, max_length=16)
    failure_arguments: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("fixture_files")
    @classmethod
    def validate_fixture_files(cls, rows: dict[str, str]) -> dict[str, str]:
        for raw_path, content in rows.items():
            path = Path(raw_path)
            if path.is_absolute() or ".." in path.parts or not raw_path.strip():
                raise ValueError("Contract fixture paths must stay inside the temporary workspace")
            if len(raw_path) > 256 or len(content.encode("utf-8")) > 64 * 1024:
                raise ValueError("Contract fixture file exceeds the bounded test limits")
        return rows

    @field_validator("cancellation_arguments")
    @classmethod
    def validate_cancellation_arguments(cls, arguments: list[str]) -> list[str]:
        if any(not argument or len(argument) > MAX_ARGUMENT_CHARS for argument in arguments):
            raise ValueError("Cancellation arguments must be non-empty bounded strings")
        return arguments

    @field_validator("failure_arguments")
    @classmethod
    def validate_failure_arguments(cls, arguments: list[str]) -> list[str]:
        if any(not argument or len(argument) > MAX_ARGUMENT_CHARS for argument in arguments):
            raise ValueError("Failure arguments must be non-empty bounded strings")
        return arguments

    @field_validator("expected_event_types")
    @classmethod
    def validate_event_types(cls, event_types: list[str]) -> list[str]:
        from swiftagent.models.agent import AgentEventType

        allowed = {event_type.value for event_type in AgentEventType}
        unknown = sorted(set(event_types) - allowed)
        if unknown:
            raise ValueError(f"Unknown normalized event types: {unknown}")
        return list(dict.fromkeys(event_types))


class AdapterManifest(ManifestModel):
    """One local out-of-process adapter using SwiftAgent's stable ACP client."""

    schema_version: Literal[1] = 1
    adapter_api_version: str
    agent_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    adapter_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    adapter_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    protocol: Literal["acp-v1"] = "acp-v1"
    command: list[str] = Field(min_length=1, max_length=MAX_COMMAND_ARGUMENTS)
    environment_allowlist: list[str] = Field(default_factory=list, max_length=64)
    state_directories: list[str] = Field(default_factory=list, max_length=16)
    capabilities: AgentCapabilities
    version_probe: VersionProbe | None = None
    compatibility: CompatibilityDeclaration | None = None
    contract: ContractFixture | None = None
    documentation_url: str | None = Field(default=None, max_length=2_048)
    install_url: str | None = Field(default=None, max_length=2_048)

    @field_validator("adapter_api_version")
    @classmethod
    def validate_api_version(cls, version: str) -> str:
        if version != ADAPTER_API_VERSION:
            raise ValueError(
                f"Unsupported adapter API {version!r}; SwiftAgent requires {ADAPTER_API_VERSION!r}"
            )
        return version

    @field_validator("command")
    @classmethod
    def validate_command(cls, command: list[str]) -> list[str]:
        if any(not argument or len(argument) > MAX_ARGUMENT_CHARS for argument in command):
            raise ValueError("Adapter command arguments must be non-empty bounded strings")
        executable = Path(command[0]).name.lower()
        if executable in _SHELL_EXECUTABLES:
            raise ValueError("Shell executables are not allowed; provide a literal agent argv")
        return command

    @field_validator("environment_allowlist")
    @classmethod
    def validate_environment_names(cls, names: list[str]) -> list[str]:
        if any(not _ENVIRONMENT_NAME.fullmatch(name) for name in names):
            raise ValueError("Environment allowlist entries must be valid variable names")
        return list(dict.fromkeys(names))

    @field_validator("state_directories")
    @classmethod
    def validate_state_directories(cls, rows: list[str]) -> list[str]:
        for raw_path in rows:
            path = Path(raw_path).expanduser()
            if not raw_path.strip() or not path.is_absolute() or len(raw_path) > 4_096:
                raise ValueError("State directories must be bounded absolute paths")
        return rows

    @model_validator(mode="after")
    def reject_unproved_external_isolation(self) -> AdapterManifest:
        if self.capabilities.external_sandbox == "verified":
            raise ValueError(
                "A local manifest cannot self-assign verified external isolation; use partial or unknown"
            )
        return self


def load_manifest(path: Path) -> AdapterManifest:
    """Read one bounded manifest file without following a directory scan recursively."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Adapter manifest was not found: {path}")
    if resolved.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError(f"Adapter manifest exceeds {MAX_MANIFEST_BYTES} bytes: {path}")
    return AdapterManifest.model_validate_json(resolved.read_text(encoding="utf-8"))


def resolve_command(manifest: AdapterManifest, manifest_path: Path) -> list[str]:
    """Resolve only documented local tokens; never invoke a shell."""
    manifest_directory = str(manifest_path.expanduser().resolve().parent)
    substitutions = {
        "${manifest_dir}": manifest_directory,
        "${python}": sys.executable,
    }
    return [
        argument.replace("${manifest_dir}", substitutions["${manifest_dir}"]).replace(
            "${python}", substitutions["${python}"]
        )
        for argument in manifest.command
    ]
