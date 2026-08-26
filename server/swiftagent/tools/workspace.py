"""Workspace path safety helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import HTTPException

from swiftagent.storage import settings as settings_repo


class WorkspacePathError(ValueError):
    """Raised when a path escapes the configured workspace."""


def get_workspace_dir() -> Path:
    workspace = Path(settings_repo.get_workspace_dir()).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _candidate_path(user_path: str) -> Path:
    raw = (user_path or ".").strip()
    if not raw:
        raw = "."

    workspace = get_workspace_dir()
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    else:
        resolved = (workspace / candidate).resolve(strict=False)

    # Keep explicit workspace root usable.
    if resolved == workspace:
        return resolved

    if workspace in resolved.parents:
        return resolved

    raise WorkspacePathError(f"Path escapes workspace: {raw}")


def resolve_workspace_path(user_path: str) -> Path:
    return _candidate_path(user_path)


def require_workspace_path(user_path: str) -> Path:
    try:
        return _candidate_path(user_path)
    except WorkspacePathError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def write_text_atomically(path: Path, content: str) -> None:
    """Atomically replace a UTF-8 workspace file without following partial writes."""
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path:
            try:
                Path(temporary_path).unlink(missing_ok=True)
            except OSError:
                pass
