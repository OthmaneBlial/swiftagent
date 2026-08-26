"""Reviewed manifest contract and safe command construction."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class VersionProbe(BaseModel):
    """Optional free subprocess probe; it never receives the task prompt."""

    arguments: list[str] = Field(default_factory=lambda: ["--version"], max_length=16)
    expected_output_prefix: str | None = Field(default=None, max_length=256)
    timeout_seconds: int = Field(default=5, ge=1, le=10)

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 4_096 or "\x00" in item for item in value):
            raise ValueError("Version probe arguments must be non-empty literal strings")
        return value


class GenericCommandManifest(BaseModel):
    """Schema v1 for one text-only local subprocess adapter."""

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128)
    executable: str = Field(min_length=1, max_length=4_096)
    arguments: list[str] = Field(default_factory=list, max_length=64)
    prompt_transport: Literal["stdin", "argument"] = "stdin"
    cwd_mode: Literal["task", "workspace"] = "task"
    timeout_seconds: int = Field(default=300, ge=1, le=3_600)
    environment_allowlist: list[str] = Field(
        default_factory=lambda: ["PATH", "LANG", "LC_ALL"], max_length=64
    )
    max_output_bytes: int = Field(default=1_048_576, ge=1_024, le=2_097_152)
    version_probe: VersionProbe | None = None

    @field_validator("executable")
    @classmethod
    def validate_executable(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("Executable must be a literal path or command name")
        return normalized

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, value: list[str]) -> list[str]:
        if any(len(item) > 16_384 or "\x00" in item for item in value):
            raise ValueError("Arguments exceed the safe literal limits")
        return value

    @field_validator("environment_allowlist")
    @classmethod
    def validate_environment(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not _ENV_NAME.fullmatch(item) for item in value):
            raise ValueError("Environment allowlist contains an invalid or duplicate name")
        return value

    @model_validator(mode="after")
    def validate_argument_budget(self) -> GenericCommandManifest:
        total = len(self.executable) + sum(len(item) for item in self.arguments)
        if total > 65_536:
            raise ValueError("Executable and argument template exceed 64 KiB")
        return self


def parse_manifest(raw: str) -> GenericCommandManifest | None:
    normalized = raw.strip()
    if not normalized:
        return None
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError("Generic command manifest must be valid JSON") from exc
    try:
        return GenericCommandManifest.model_validate(value)
    except Exception as exc:
        raise ValueError(f"Invalid generic command manifest: {exc}") from exc


def normalized_json(manifest: GenericCommandManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def fingerprint(manifest: GenericCommandManifest) -> str:
    return hashlib.sha256(normalized_json(manifest).encode("utf-8")).hexdigest()


def resolve_executable(manifest: GenericCommandManifest) -> str | None:
    candidate = Path(manifest.executable).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(manifest.executable)


def executable_identity(executable: str) -> str:
    path = Path(executable).resolve()
    stat = path.stat()
    raw = f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
    return hashlib.sha256(raw).hexdigest()


def build_command(
    manifest: GenericCommandManifest,
    executable: str,
    prompt: str,
) -> tuple[list[str], bytes | None]:
    command = [executable, *manifest.arguments]
    if manifest.prompt_transport == "argument":
        command.append(prompt)
        return command, None
    return command, prompt.encode("utf-8")


def allowed_environment(manifest: GenericCommandManifest) -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in manifest.environment_allowlist
        if name in os.environ
    }
