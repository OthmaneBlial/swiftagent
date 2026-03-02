"""REST API routes."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from swiftagent.models.settings import AppSettings
from swiftagent.models.task import Task
from swiftagent.storage import settings as settings_repo
from swiftagent.storage import tasks as task_repo
from swiftagent.tools.workspace import get_workspace_dir, require_workspace_path

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════════


@router.get("/tasks", response_model=list[Task])
async def list_tasks():
    return task_repo.get_tasks()


@router.get("/tasks/{task_id}", response_model=Task | None)
async def get_task(task_id: str):
    task = task_repo.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    task_repo.delete_task(task_id)
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
    claude_model: str | None = None
    claude_permission_mode: str | None = None
    claude_cli_path: str | None = None
    workspace_dir: str | None = None
    sandbox_mode: Literal["strict", "fallback"] | None = None


@router.put("/settings", response_model=AppSettings)
async def update_settings(update: SettingsUpdate):
    if update.debug_mode is not None:
        settings_repo.set_debug_mode(update.debug_mode)
    if update.theme is not None:
        settings_repo.set_theme(update.theme)
    if update.claude_model is not None:
        settings_repo.set_claude_model(update.claude_model)
    if update.claude_permission_mode is not None:
        mode = update.claude_permission_mode.strip() or "default"
        settings_repo.set_claude_permission_mode(mode)
    if update.claude_cli_path is not None:
        settings_repo.set_claude_cli_path(update.claude_cli_path or None)
    if update.workspace_dir is not None:
        raw_workspace = update.workspace_dir.strip()
        if not raw_workspace:
            raise HTTPException(400, "workspace_dir cannot be empty")
        path = Path(raw_workspace).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        settings_repo.set_workspace_dir(str(path))
    if update.sandbox_mode is not None:
        settings_repo.set_sandbox_mode(update.sandbox_mode)

    return settings_repo.get_app_settings()


# ═══════════════════════════════════════════════════════════════
# Engine status
# ═══════════════════════════════════════════════════════════════


_AUTH_PROBE_CACHE: dict[str, str | None] = {
    "status": "not_checked",
    "message": None,
    "checked_at": None,
}


def _resolve_claude_path() -> str | None:
    configured = settings_repo.get_claude_cli_path()
    if configured:
        return configured
    return shutil.which("claude")


def _probe_auth(claude_path: str | None, model: str | None) -> tuple[str, str | None]:
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
    except Exception as e:  # pragma: no cover - defensive
        return "error", str(e)

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


@router.get("/engine/status")
async def engine_status(probe_auth: bool = Query(default=False)):
    claude_path = _resolve_claude_path()
    bwrap_available = shutil.which("bwrap") is not None
    sandbox_mode = settings_repo.get_sandbox_mode()
    strict_active = sandbox_mode == "strict" and bwrap_available

    degraded = sandbox_mode == "strict" and not bwrap_available
    degraded_reason = (
        "sandbox_mode is strict but bwrap is unavailable; fallback sandboxing is active"
        if degraded
        else None
    )

    if probe_auth:
        status, message = _probe_auth(claude_path, settings_repo.get_claude_model())
        _AUTH_PROBE_CACHE["status"] = status
        _AUTH_PROBE_CACHE["message"] = message
        _AUTH_PROBE_CACHE["checked_at"] = datetime.now(UTC).isoformat()

    return {
        "claude_cli_available": claude_path is not None,
        "claude_cli_path": claude_path,
        "bwrap_available": bwrap_available,
        "workspace_dir": settings_repo.get_workspace_dir(),
        "sandbox_mode": sandbox_mode,
        "strict_sandbox_active": strict_active,
        "degraded": degraded,
        "degraded_reason": degraded_reason,
        "auth_probe": _AUTH_PROBE_CACHE,
    }


# ═══════════════════════════════════════════════════════════════
# Files (workspace scoped)
# ═══════════════════════════════════════════════════════════════


class FileWriteBody(BaseModel):
    path: str
    content: str
    create_parents: bool = True


class FileMkdirBody(BaseModel):
    path: str
    parents: bool = True


class FileMoveBody(BaseModel):
    source_path: str
    target_path: str
    create_parents: bool = True


class FileDeleteBody(BaseModel):
    path: str
    recursive: bool = False


class FileReadBody(BaseModel):
    path: str


def _to_workspace_relative(path: Path) -> str:
    workspace = get_workspace_dir()
    rel = path.relative_to(workspace)
    return "." if str(rel) == "." or str(rel) == "" else rel.as_posix()


@router.get("/files/workspace")
async def files_workspace():
    workspace = get_workspace_dir()
    return {"workspace": str(workspace), "path": "."}


@router.get("/files/list")
async def files_list(path: str = Query(default=".")):
    directory = require_workspace_path(path)
    if not directory.exists():
        raise HTTPException(404, "Directory not found")
    if not directory.is_dir():
        raise HTTPException(400, "Path is not a directory")

    entries = []
    for entry in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        stat = entry.stat()
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
        "parent": None if directory == get_workspace_dir() else _to_workspace_relative(directory.parent),
        "entries": entries,
    }


@router.post("/files/read")
async def files_read(body: FileReadBody):
    file_path = require_workspace_path(body.path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found")

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
    file_path.write_text(body.content, encoding="utf-8")

    return {"ok": True, "path": _to_workspace_relative(file_path)}


@router.post("/files/mkdir")
async def files_mkdir(body: FileMkdirBody):
    directory = require_workspace_path(body.path)
    directory.mkdir(parents=body.parents, exist_ok=True)
    return {"ok": True, "path": _to_workspace_relative(directory)}


@router.post("/files/move")
async def files_move(body: FileMoveBody):
    source = require_workspace_path(body.source_path)
    target = require_workspace_path(body.target_path)
    if not source.exists():
        raise HTTPException(404, "Source path not found")

    if body.create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)

    source.rename(target)
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

    if path.is_dir():
        if body.recursive:
            shutil.rmtree(path)
        else:
            path.rmdir()
    else:
        path.unlink()

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
