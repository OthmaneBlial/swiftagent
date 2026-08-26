#!/usr/bin/env python3
"""Start one SwiftAgent task and print its event stream."""

from __future__ import annotations

import argparse
import asyncio
import json
import os

from websockets.asyncio.client import connect


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", help="agent id; otherwise use SwiftAgent's saved default")
    parser.add_argument("prompt", nargs="+")
    arguments = parser.parse_args()
    prompt = " ".join(arguments.prompt).strip()

    url = os.environ.get("SWIFTAGENT_WS_URL", "ws://127.0.0.1:8000/ws")
    async with connect(url) as websocket:
        payload = {"prompt": prompt}
        if arguments.agent:
            payload["agent_id"] = arguments.agent
        await websocket.send(json.dumps({"type": "task:start", "payload": payload}))
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
