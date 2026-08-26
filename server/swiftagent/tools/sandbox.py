"""Sandbox capability helpers."""

from __future__ import annotations

import shutil
import subprocess
import time
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
