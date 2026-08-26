#!/usr/bin/env python3
"""Deterministic Claude stream-json CLI fixture; never performs inference."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> None:
    if sys.argv[1:] == ["--version"]:
        print("2.1.52 (Claude Code fixture)")
        return
    log_path = os.environ.get("SWIFTAGENT_TEST_CLAUDE_LOG")
    if log_path:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"args": sys.argv[1:]}) + "\n")
    if os.environ.get("SWIFTAGENT_TEST_CLAUDE_SCENARIO") == "cancel":
        time.sleep(60)
        return
    fixture = Path(__file__).with_name("successful_run.jsonl")
    sys.stdout.write(fixture.read_text(encoding="utf-8"))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
