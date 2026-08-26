#!/usr/bin/env python3
"""No-network text subprocess fixture for the restricted generic adapter."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def record() -> None:
    target = os.environ.get("SWIFTAGENT_TEST_GENERIC_LOG")
    if not target:
        return
    payload = {
        "argv": sys.argv[1:],
        "cwd": os.getcwd(),
        "environment": sorted(os.environ),
    }
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> None:
    if sys.argv[1:] == ["--version"]:
        print("generic-fixture 1.0.0")
        return

    record()
    scenario = os.environ.get("SWIFTAGENT_TEST_GENERIC_SCENARIO", "basic")
    if scenario == "sleep":
        time.sleep(60)
        return
    if scenario == "fail":
        print("fixture failure", file=sys.stderr)
        raise SystemExit(7)
    if scenario == "spam":
        print("x" * 65_536)
        return
    if scenario == "stderr":
        print("bounded diagnostic", file=sys.stderr)

    if sys.argv[1:2] == ["--argument"]:
        prompt = sys.argv[2] if len(sys.argv) > 2 else ""
    else:
        prompt = sys.stdin.read()
    if "SWIFTAGENT_ADAPTER_OK" in prompt:
        print("SWIFTAGENT_ADAPTER_OK")
    else:
        print(f"generic:{prompt}")


if __name__ == "__main__":
    main()
