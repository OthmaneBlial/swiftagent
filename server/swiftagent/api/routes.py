"""REST API routes."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from swiftagent.agents.acp import settings as acp_settings
from swiftagent.agents.codex import settings as codex_settings
from swiftagent.agents.generic_command import settings as generic_command_settings
from swiftagent.agents.generic_command.tester import run_disposable_test
from swiftagent.agents.opencode import settings as opencode_settings
from swiftagent.agents.registry import agent_registry
from swiftagent.handoff import create_preview, start_handoff
from swiftagent.models.handoff import HandoffPreview, HandoffPreviewRequest
from swiftagent.models.receipt import RunReceipt, VerificationEvidence
from swiftagent.models.settings import AppSettings
from swiftagent.models.task import Task
from swiftagent.storage import receipts as receipt_repo
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.workspace import (
    get_workspace_dir,
    require_workspace_path,
    write_text_atomically,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════════


@router.get("/tasks", response_model=list[Task])
async def list_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return task_repo.get_tasks(limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=Task | None)
async def get_task(task_id: str):
    task = task_repo.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/tasks/{task_id}/receipt", response_model=RunReceipt)
async def get_run_receipt(task_id: str):
    receipt = receipt_repo.get_receipt(task_id)
    if receipt is None:
        raise HTTPException(404, "Run receipt not found")
    return receipt


class VerificationUpdate(BaseModel):
    status: Literal["passed", "failed", "not_run"]
    summary: str | None = Field(default=None, max_length=4_096)
    command: str | None = Field(default=None, max_length=4_096)


@router.put("/tasks/{task_id}/receipt/verification", response_model=RunReceipt)
async def update_run_verification(task_id: str, update: VerificationUpdate):
    if update.status != "not_run" and not (update.summary or "").strip():
        raise HTTPException(400, "Verification evidence is required for passed or failed")
    if task_repo.get_task(task_id) is None:
        raise HTTPException(404, "Task not found")
    summary = (update.summary or "").strip() or None if update.status != "not_run" else None
    command = (update.command or "").strip() or None if update.status != "not_run" else None
    evidence = VerificationEvidence(
        status=update.status,
        summary=summary,
        command=command,
        source="user",
        recorded_at=datetime.now(UTC),
    )
    try:
        receipt_repo.record_verification(task_id, evidence)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    receipt = receipt_repo.get_receipt(task_id)
    if receipt is None:  # pragma: no cover - guarded by persistence update
        raise HTTPException(404, "Run receipt not found")
    return receipt


@router.get("/tasks/{task_id}/receipt/export")
async def export_run_receipt(
    task_id: str,
    format: Literal["json", "markdown"] = Query(default="json"),
):
    receipt = receipt_repo.get_receipt(task_id)
    if receipt is None:
        raise HTTPException(404, "Run receipt not found")
    if format == "markdown":
        content = receipt_repo.receipt_as_markdown(receipt)
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    else:
        content = receipt.model_dump_json(indent=2)
        media_type = "application/json"
        extension = "json"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="swiftagent-receipt-{task_id}.{extension}"'
        },
    )


@router.post("/tasks/{task_id}/handoff/preview", response_model=HandoffPreview)
async def preview_cross_agent_handoff(task_id: str, request: HandoffPreviewRequest):
    try:
        return create_preview(task_id, request)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code, message) from exc


@router.post("/handoffs/{handoff_id}/start", response_model=Task)
async def execute_cross_agent_handoff(handoff_id: str):
    try:
        return await start_handoff(handoff_id)
    except (OSError, RuntimeError, ValueError) as exc:
        message = str(exc)
        if "not found" in message.lower():
            status_code = 404
        elif "already used" in message.lower() or "expired" in message.lower():
            status_code = 409
        else:
            status_code = 400
        raise HTTPException(status_code, message) from exc


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    if not task_repo.delete_task(task_id):
        raise HTTPException(404, "Task not found")
    return {"ok": True}


@router.delete("/tasks")
async def clear_history():
    task_repo.clear_history()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════


@router.get("/settings", response_model=AppSettings)
async def get_settings():
    return settings_repo.get_app_settings()


class SettingsUpdate(BaseModel):
    debug_mode: bool | None = None
    theme: Literal["light", "dark", "system"] | None = None
    default_agent_id: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"
    )
    claude_model: str | None = Field(default=None, max_length=256)
    claude_permission_mode: (
        Literal["default", "acceptEdits", "dontAsk", "bypassPermissions", "plan"] | None
    ) = None
    claude_cli_path: str | None = Field(default=None, max_length=4_096)
    acp_command_json: str | None = Field(default=None, max_length=16_384)
    codex_model: str | None = Field(default=None, max_length=256)
    codex_cli_path: str | None = Field(default=None, max_length=4_096)
    codex_approval_policy: Literal["untrusted", "on-request", "never"] | None = None
    codex_sandbox_mode: (
        Literal["read-only", "workspace-write", "danger-full-access"] | None
    ) = None
    codex_allow_dangerous_bypass: bool | None = None
    opencode_model: str | None = Field(default=None, max_length=256)
    opencode_cli_path: str | None = Field(default=None, max_length=4_096)
    generic_command_manifest_json: str | None = Field(default=None, max_length=65_536)
    workspace_dir: str | None = Field(default=None, max_length=4_096)
    sandbox_mode: Literal["strict", "fallback"] | None = None


@router.put("/settings", response_model=AppSettings)
async def update_settings(update: SettingsUpdate):
    prospective_codex_approval = (
        update.codex_approval_policy or codex_settings.get_approval_policy()
    )
    prospective_codex_sandbox = update.codex_sandbox_mode or codex_settings.get_sandbox_mode()
    prospective_dangerous_bypass = (
        update.codex_allow_dangerous_bypass
        if update.codex_allow_dangerous_bypass is not None
        else codex_settings.get_allow_dangerous_bypass()
    )
    try:
        codex_settings.validate_safety_combination(
            prospective_codex_approval,
            prospective_codex_sandbox,
            prospective_dangerous_bypass,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if update.debug_mode is not None:
        settings_repo.set_debug_mode(update.debug_mode)
    if update.theme is not None:
        settings_repo.set_theme(update.theme)
    if update.default_agent_id is not None:
        try:
            agent_registry.definition(update.default_agent_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        settings_repo.set_default_agent_id(update.default_agent_id)
    if update.claude_model is not None:
        settings_repo.set_claude_model(update.claude_model)
    if update.claude_permission_mode is not None:
        mode = update.claude_permission_mode.strip() or "default"
        settings_repo.set_claude_permission_mode(mode)
    if update.claude_cli_path is not None:
        settings_repo.set_claude_cli_path(update.claude_cli_path or None)
    if update.acp_command_json is not None:
        raw_command = update.acp_command_json.strip()
        if not raw_command:
            acp_settings.set_command(None)
        else:
            try:
                command = acp_settings.parse_command(raw_command)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            acp_settings.set_command(command)
    if update.codex_model is not None:
        codex_settings.set_model(update.codex_model or None)
    if update.codex_cli_path is not None:
        codex_settings.set_cli_path(update.codex_cli_path or None)
    if update.codex_approval_policy is not None:
        codex_settings.set_approval_policy(update.codex_approval_policy)
    if update.codex_sandbox_mode is not None:
        codex_settings.set_sandbox_mode(update.codex_sandbox_mode)
    if update.codex_allow_dangerous_bypass is not None:
        codex_settings.set_allow_dangerous_bypass(update.codex_allow_dangerous_bypass)
    if update.opencode_model is not None:
        opencode_settings.set_model(update.opencode_model or None)
    if update.opencode_cli_path is not None:
        opencode_settings.set_cli_path(update.opencode_cli_path or None)
    if update.generic_command_manifest_json is not None:
        try:
            generic_command_settings.set_manifest_json(update.generic_command_manifest_json)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if update.workspace_dir is not None:
        raw_workspace = update.workspace_dir.strip()
        if not raw_workspace:
            raise HTTPException(400, "workspace_dir cannot be empty")
        path = Path(raw_workspace).expanduser().resolve()
        if path == path.parent or path == Path.home().resolve():
            raise HTTPException(
                400,
                "workspace_dir cannot be the filesystem or home directory root; choose a dedicated workspace",
            )
        path.mkdir(parents=True, exist_ok=True)
        settings_repo.set_workspace_dir(str(path))
    if update.sandbox_mode is not None:
        settings_repo.set_sandbox_mode(update.sandbox_mode)

    return settings_repo.get_app_settings()


# ═══════════════════════════════════════════════════════════════
# Agents
# ═══════════════════════════════════════════════════════════════


@router.get("/agents")
async def list_agents(refresh: bool = Query(default=False)):
    """Return read-only local readiness and declared capabilities."""
    return {
        "default_agent_id": settings_repo.get_default_agent_id(),
        "agents": agent_registry.statuses(refresh=refresh),
    }


@router.post("/agents/generic-command/test")
async def test_generic_command_adapter():
    try:
        return await run_disposable_test()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/engine/status")
async def engine_status(probe_auth: bool = Query(default=False)):
    from swiftagent.agents.claude.status import get_legacy_engine_status

    return get_legacy_engine_status(probe_authentication=probe_auth)


# ═══════════════════════════════════════════════════════════════
# Files (workspace scoped)
# ═══════════════════════════════════════════════════════════════


class FileWriteBody(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    content: str
    create_parents: bool = True


class FileMkdirBody(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    parents: bool = True


class FileMoveBody(BaseModel):
    source_path: str = Field(min_length=1, max_length=4_096)
    target_path: str = Field(min_length=1, max_length=4_096)
    create_parents: bool = True


class FileDeleteBody(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)
    recursive: bool = False


class FileReadBody(BaseModel):
    path: str = Field(min_length=1, max_length=4_096)


def _max_file_bytes() -> int:
    raw = os.environ.get("SWIFTAGENT_MAX_FILE_BYTES", "1048576")
    try:
        value = int(raw)
    except ValueError:
        return 1_048_576
    return min(max(value, 1_024), 25 * 1_024 * 1_024)


def _max_directory_entries() -> int:
    raw = os.environ.get("SWIFTAGENT_MAX_DIRECTORY_ENTRIES", "500")
    try:
        value = int(raw)
    except ValueError:
        return 500
    return min(max(value, 10), 5_000)


def _ensure_not_workspace_root(path: Path, action: str) -> None:
    if path == get_workspace_dir():
        raise HTTPException(400, f"Cannot {action} the workspace root")


def _to_workspace_relative(path: Path) -> str:
    workspace = get_workspace_dir()
    rel = path.relative_to(workspace)
    return "." if str(rel) == "." or str(rel) == "" else rel.as_posix()


@router.get("/files/workspace")
async def files_workspace():
    workspace = get_workspace_dir()
    return {"workspace": str(workspace), "path": "."}


@router.get("/files/list")
async def files_list(
    path: str = Query(default="."),
    limit: int = Query(default=200, ge=1, le=5_000),
):
    directory = require_workspace_path(path)
    if not directory.exists():
        raise HTTPException(404, "Directory not found")
    if not directory.is_dir():
        raise HTTPException(400, "Path is not a directory")

    safe_limit = min(limit, _max_directory_entries())
    entries = []
    ordered_entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    for entry in ordered_entries[:safe_limit]:
        try:
            stat = entry.stat()
        except OSError:
            # A file can disappear between listing and stat; omit it rather than failing the whole view.
            continue
        entries.append(
            {
                "name": entry.name,
                "path": _to_workspace_relative(entry),
                "type": "directory" if entry.is_dir() else "file",
                "size": stat.st_size if entry.is_file() else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )

    return {
        "path": _to_workspace_relative(directory),
        "parent": None
        if directory == get_workspace_dir()
        else _to_workspace_relative(directory.parent),
        "entries": entries,
        "truncated": len(ordered_entries) > safe_limit,
    }


@router.post("/files/read")
async def files_read(body: FileReadBody):
    file_path = require_workspace_path(body.path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found")
    size = file_path.stat().st_size
    if size > _max_file_bytes():
        raise HTTPException(
            413,
            f"File is too large to open in SwiftAgent ({size} bytes; limit is {_max_file_bytes()} bytes)",
        )

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(400, "File is not UTF-8 text") from e

    return {
        "path": _to_workspace_relative(file_path),
        "content": content,
    }


@router.post("/files/write")
async def files_write(body: FileWriteBody):
    file_path = require_workspace_path(body.path)
    if file_path.exists() and file_path.is_dir():
        raise HTTPException(400, "Cannot overwrite a directory with file content")
    if body.create_parents:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    size = len(body.content.encode("utf-8"))
    if size > _max_file_bytes():
        raise HTTPException(
            413,
            f"File content is too large to save ({size} bytes; limit is {_max_file_bytes()} bytes)",
        )
    try:
        write_text_atomically(file_path, body.content)
    except OSError as exc:
        raise HTTPException(
            500, "Could not save file. Check workspace permissions and free space."
        ) from exc

    return {"ok": True, "path": _to_workspace_relative(file_path)}


@router.post("/files/mkdir")
async def files_mkdir(body: FileMkdirBody):
    directory = require_workspace_path(body.path)
    try:
        directory.mkdir(parents=body.parents, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            409, "Could not create directory. Check its parent path and permissions."
        ) from exc
    return {"ok": True, "path": _to_workspace_relative(directory)}


@router.post("/files/move")
async def files_move(body: FileMoveBody):
    source = require_workspace_path(body.source_path)
    target = require_workspace_path(body.target_path)
    if not source.exists():
        raise HTTPException(404, "Source path not found")
    _ensure_not_workspace_root(source, "move")
    if source == target:
        raise HTTPException(400, "Source and target paths must be different")
    if target.exists():
        raise HTTPException(409, "Target path already exists; choose a new name")
    if source.is_dir() and source in target.parents:
        raise HTTPException(400, "Cannot move a directory into itself")

    if body.create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)

    try:
        source.rename(target)
    except OSError as exc:
        raise HTTPException(
            409, "Could not move this path. Check the target parent and permissions."
        ) from exc
    return {
        "ok": True,
        "source_path": _to_workspace_relative(source),
        "target_path": _to_workspace_relative(target),
    }


@router.post("/files/delete")
async def files_delete(body: FileDeleteBody):
    path = require_workspace_path(body.path)
    if not path.exists():
        raise HTTPException(404, "Path not found")
    _ensure_not_workspace_root(path, "delete")

    if path.is_dir():
        try:
            if body.recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()
        except OSError as exc:
            raise HTTPException(
                409,
                "Directory is not empty or could not be removed. Enable recursive deletion only after reviewing its contents.",
            ) from exc
    else:
        try:
            path.unlink()
        except OSError as exc:
            raise HTTPException(409, "Could not delete file. Check workspace permissions.") from exc

    return {"ok": True, "path": _to_workspace_relative(path)}


# ═══════════════════════════════════════════════════════════════
# Deprecated provider/key APIs
# ═══════════════════════════════════════════════════════════════


def _providers_removed() -> None:
    raise HTTPException(
        status_code=410,
        detail="Provider/key APIs were removed in Claude-only mode. Use /settings and /engine/status.",
    )


@router.get("/providers")
async def deprecated_get_providers():
    _providers_removed()


@router.get("/providers/catalog")
async def deprecated_get_provider_catalog():
    _providers_removed()


@router.get("/providers/models/{provider_id}")
async def deprecated_get_models(provider_id: str):
    _providers_removed()


@router.post("/providers/{provider_id}/connect")
async def deprecated_connect_provider(provider_id: str):
    _providers_removed()


@router.post("/providers/{provider_id}/disconnect")
async def deprecated_disconnect_provider(provider_id: str):
    _providers_removed()


@router.put("/providers/active")
async def deprecated_set_active_provider():
    _providers_removed()


@router.put("/providers/ollama/config")
async def deprecated_update_ollama_config():
    _providers_removed()


@router.get("/providers/ollama/config")
async def deprecated_get_ollama_config():
    _providers_removed()


@router.get("/onboard/status")
async def deprecated_onboard_status():
    _providers_removed()


@router.post("/keys/{provider}")
async def deprecated_store_api_key(provider: str):
    _providers_removed()


@router.get("/keys/{provider}")
async def deprecated_get_api_key(provider: str):
    _providers_removed()


@router.delete("/keys/{provider}")
async def deprecated_delete_api_key(provider: str):
    _providers_removed()


@router.get("/keys")
async def deprecated_list_api_keys():
    _providers_removed()
