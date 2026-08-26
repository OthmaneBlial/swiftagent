"""Codex adapter settings in SwiftAgent's local key-value store."""

from __future__ import annotations

import os
from typing import Literal, cast

from swiftagent.storage import settings as settings_repo

ApprovalPolicy = Literal["untrusted", "on-request", "never"]
SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]


def get_cli_path() -> str | None:
    value = settings_repo.get_value(
        "codex_cli_path", os.environ.get("SWIFTAGENT_CODEX_PATH", "")
    ).strip()
    return value or None


def set_cli_path(path: str | None) -> None:
    settings_repo.set_value("codex_cli_path", (path or "").strip())


def get_model() -> str | None:
    value = settings_repo.get_value("codex_model", "").strip()
    return value or None


def set_model(model: str | None) -> None:
    settings_repo.set_value("codex_model", (model or "").strip())


def get_approval_policy() -> ApprovalPolicy:
    value = settings_repo.get_value("codex_approval_policy", "on-request").strip()
    return cast(ApprovalPolicy, value if value in {"untrusted", "on-request", "never"} else "on-request")


def set_approval_policy(policy: ApprovalPolicy) -> None:
    settings_repo.set_value("codex_approval_policy", policy)


def get_sandbox_mode() -> SandboxMode:
    value = settings_repo.get_value("codex_sandbox_mode", "workspace-write").strip()
    return cast(
        SandboxMode,
        value if value in {"read-only", "workspace-write", "danger-full-access"} else "workspace-write",
    )


def set_sandbox_mode(mode: SandboxMode) -> None:
    settings_repo.set_value("codex_sandbox_mode", mode)


def get_allow_dangerous_bypass() -> bool:
    return settings_repo.get_value("codex_allow_dangerous_bypass", "0") == "1"


def set_allow_dangerous_bypass(allowed: bool) -> None:
    settings_repo.set_value("codex_allow_dangerous_bypass", "1" if allowed else "0")


def validate_safety_combination(
    approval_policy: ApprovalPolicy,
    sandbox_mode: SandboxMode,
    allow_dangerous_bypass: bool,
) -> None:
    if (
        approval_policy == "never"
        and sandbox_mode == "danger-full-access"
        and not allow_dangerous_bypass
    ):
        raise ValueError(
            "Codex approval 'never' plus sandbox 'danger-full-access' disables both native safety "
            "layers. Explicitly confirm the dangerous bypass before saving."
        )
