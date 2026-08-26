"""Sandbox capability helpers."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

_BWRAP_CACHE_TTL_SEC = 30.0
_bwrap_cache: dict[str, object] = {
    "checked_at": 0.0,
    "path": None,
    "workspace": None,
    "usable": False,
    "reason": "not_checked",
}


def _cache_valid(bwrap_path: str | None, workspace: Path) -> bool:
    checked_at = float(_bwrap_cache.get("checked_at", 0.0))
    if time.monotonic() - checked_at > _BWRAP_CACHE_TTL_SEC:
        return False
    return _bwrap_cache.get("path") == bwrap_path and _bwrap_cache.get("workspace") == str(
        workspace
    )


def check_bwrap_usable(workspace: Path) -> tuple[bool, str | None]:
    """Return whether bwrap can run in this environment."""
    bwrap_path = shutil.which("bwrap")
    if not bwrap_path:
        return False, "bwrap not found"

    if _cache_valid(bwrap_path, workspace):
        return bool(_bwrap_cache["usable"]), _bwrap_cache.get("reason") or None

    probe = [
        bwrap_path,
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--chdir",
        str(workspace),
        "/bin/true",
    ]

    try:
        proc = subprocess.run(
            probe,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as e:  # pragma: no cover - defensive
        usable = False
        reason = str(e)
    else:
        usable = proc.returncode == 0
        if usable:
            reason = None
        else:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            reason = stderr or stdout or f"bwrap exited with code {proc.returncode}"

    _bwrap_cache["checked_at"] = time.monotonic()
    _bwrap_cache["path"] = bwrap_path
    _bwrap_cache["workspace"] = str(workspace)
    _bwrap_cache["usable"] = usable
    _bwrap_cache["reason"] = reason

    return usable, reason


def wrap_command_for_sandbox(
    command: Sequence[str],
    workspace: Path,
    sandbox_mode: str,
    *,
    writable_paths: Sequence[Path] = (),
) -> tuple[list[str], str | None]:
    """Wrap a literal argv for strict bwrap isolation or explicit fallback."""
    argv = [str(part) for part in command]
    if not argv:
        raise ValueError("Command cannot be empty")
    if sandbox_mode != "strict":
        return argv, "Fallback mode is active. This process is not OS-isolated."

    bwrap_path = shutil.which("bwrap")
    if not bwrap_path:
        raise RuntimeError(
            "Strict sandbox is unavailable because bwrap is not installed. "
            "Install bwrap, or explicitly select fallback mode after reviewing its warning."
        )
    usable, reason = check_bwrap_usable(workspace)
    if not usable:
        raise RuntimeError(
            "Strict sandbox is unavailable in this environment "
            f"({reason or 'unknown error'}). Repair bwrap or explicitly select fallback mode."
        )

    wrapped = [
        bwrap_path,
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(workspace),
        str(workspace),
    ]
    for writable in writable_paths:
        resolved = writable.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        wrapped.extend(["--bind", str(resolved), str(resolved)])
    wrapped.extend(["--chdir", str(workspace), *argv])
    return wrapped, None
