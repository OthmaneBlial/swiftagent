#!/usr/bin/env python3
"""Start one SwiftAgent task and print its event stream."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from websockets.asyncio.client import connect


async def main() -> int:
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        print("Usage: python3 start_task.py <prompt>", file=sys.stderr)
        return 2

    url = os.environ.get("SWIFTAGENT_WS_URL", "ws://127.0.0.1:8000/ws")
    async with connect(url) as websocket:
        await websocket.send(json.dumps({"type": "task:start", "payload": {"prompt": prompt}}))
        task_id: str | None = None
        async for raw_event in websocket:
            event = json.loads(raw_event)
            if event["type"] == "task:started":
                task_id = event.get("task_id") or event["payload"].get("id")
            if task_id and event.get("task_id") not in {None, task_id}:
                continue
            print(json.dumps(event, ensure_ascii=False))
            if event["type"] == "task:complete":
                return 0 if event["payload"].get("success") else 1
            if event["type"] == "task:error" and not task_id:
                return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
