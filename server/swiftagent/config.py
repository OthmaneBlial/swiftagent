"""
Environment configuration helpers.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_dotenv(dotenv_path: str | Path | None = None) -> Path | None:
    if dotenv_path is not None:
        path = Path(dotenv_path)
        return path if path.is_file() else None

    candidates = [
        Path(__file__).resolve().parents[2] / ".env",  # server/../.env
        Path.cwd() / ".env",
        Path.home() / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _strip_inline_comment(value: str) -> str:
    """Strip inline comments while respecting quoted strings."""
    in_single = False
    in_double = False
    escaped = False
    out: list[str] = []
    for ch in value:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).strip()


def load_dotenv(dotenv_path: str | Path | None = None) -> None:
    """Load .env variables into ``os.environ`` without overriding existing values."""
    path = _find_dotenv(dotenv_path)
    if path is None:
        return

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, _, raw_value = line.partition("=")
            key = key.strip()
            value = _strip_inline_comment(raw_value.strip())

            # Remove matching quotes after stripping comments.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]

            if key and key not in os.environ:
                os.environ[key] = value
