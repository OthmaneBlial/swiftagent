"""Claude Code native state paths used by its sandbox wrapper."""

from __future__ import annotations

import os
from pathlib import Path


def get_state_dir() -> Path:
    configured = os.environ.get("SWIFTAGENT_CLAUDE_STATE_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".claude"
