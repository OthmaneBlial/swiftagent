"""Deterministic Codex app-server v2 JSONL fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class FakeAppServer:
    def __init__(self, scenario: str, log_path: Path | None):
        self.scenario = scenario
        self.log_path = log_path
        self.thread_id = "codex-fixture-thread"
        self.turn_id = "codex-fixture-turn"

    def send(self, message: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def record(self, message: dict[str, Any]) -> None:
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, separators=(",", ":")) + "\n")

    def respond(self, request_id: int, result: dict[str, Any]) -> None:
        self.send({"id": request_id, "result": result})

    def run(self) -> None:
        for line in sys.stdin:
            message = json.loads(line)
            self.record(message)
            method = message.get("method")
            request_id = message.get("id")
            if method == "initialize":
                self.respond(
                    request_id,
                    {
                        "userAgent": "codex-cli/0.149.1 fixture",
                        "platformFamily": "unix",
                        "platformOs": "fixture",
                        "codexHome": "/tmp/codex-fixture",
                    },
                )
            elif method == "initialized":
                continue
            elif method == "account/read":
                self.respond(
                    request_id,
                    {
                        "account": {
                            "type": "chatgpt",
                            "email": None,
                            "planType": "unknown",
                        },
                        "requiresOpenaiAuth": True,
                    },
                )
            elif method == "model/list":
                self.respond(
                    request_id,
                    {
                        "data": [
                            {
                                "id": "fixture-model",
                                "model": "fixture-model",
                                "displayName": "Fixture Model",
                                "isDefault": True,
                            }
                        ],
                        "nextCursor": None,
                    },
                )
            elif method in {"thread/start", "thread/resume"}:
                self.respond(
                    request_id,
                    {
                        "thread": {"id": self.thread_id},
                        "model": "fixture-model",
                        "modelProvider": "fixture",
                        "cwd": message.get("params", {}).get("cwd"),
                        "approvalPolicy": "on-request",
                        "approvalsReviewer": "user",
                        "sandbox": {"type": "workspaceWrite"},
                    },
                )
            elif method == "turn/start":
                self._start_turn(request_id)
            elif method == "turn/interrupt":
                self.respond(request_id, {})
                self._complete_turn("interrupted")
            elif request_id == "fixture-approval":
                decision = (message.get("result") or {}).get("decision")
                if decision == "accept":
                    self._finish_success()
                else:
                    self._finish_rejected()

    def _start_turn(self, request_id: int) -> None:
        self.respond(
            request_id,
            {"turn": {"id": self.turn_id, "items": [], "status": "inProgress"}},
        )
        self.send(
            {
                "method": "turn/started",
                "params": {
                    "threadId": self.thread_id,
                    "turn": {"id": self.turn_id, "items": [], "status": "inProgress"},
                },
            }
        )
        if self.scenario == "cancel":
            return
        if self.scenario == "malformed":
            sys.stdout.write("{malformed json\n")
            sys.stdout.flush()
            return
        self.send(
            {
                "method": "item/started",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "startedAtMs": 1,
                    "item": {
                        "id": "fixture-command",
                        "type": "commandExecution",
                        "command": "printf fixture",
                        "commandActions": [],
                        "cwd": "/workspace",
                        "status": "inProgress",
                    },
                },
            }
        )
        if self.scenario == "tool-failure":
            self._finish_success(tool_failed=True)
            return
        self.send(
            {
                "method": "item/commandExecution/requestApproval",
                "id": "fixture-approval",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "itemId": "fixture-command",
                    "startedAtMs": 1,
                    "command": "printf fixture",
                    "cwd": "/workspace",
                    "reason": "Exercise the native Codex approval flow",
                },
            }
        )

    def _finish_success(self, *, tool_failed: bool = False) -> None:
        self.send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "completedAtMs": 2,
                    "item": {
                        "id": "fixture-command",
                        "type": "commandExecution",
                        "command": "printf fixture",
                        "commandActions": [],
                        "cwd": "/workspace",
                        "status": "failed" if tool_failed else "completed",
                        "exitCode": 1 if tool_failed else 0,
                        "aggregatedOutput": "fixture output",
                    },
                },
            }
        )
        self.send(
            {
                "method": "turn/plan/updated",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "plan": [{"step": "Exercise app-server", "status": "completed"}],
                },
            }
        )
        self.send(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "tokenUsage": {"total": {"totalTokens": 42}},
                },
            }
        )
        text = "Codex fixture completed after a tool failure." if tool_failed else "Codex fixture completed."
        for delta in (text[:12], text[12:]):
            self.send(
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": self.thread_id,
                        "turnId": self.turn_id,
                        "itemId": "fixture-message",
                        "delta": delta,
                    },
                }
            )
        self.send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "completedAtMs": 3,
                    "item": {
                        "id": "fixture-message",
                        "type": "agentMessage",
                        "text": text,
                        "phase": "final_answer",
                    },
                },
            }
        )
        self.send({"method": "future/unknown", "params": {"threadId": self.thread_id}})
        self._complete_turn("completed")

    def _finish_rejected(self) -> None:
        self.send(
            {
                "method": "item/completed",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "completedAtMs": 2,
                    "item": {
                        "id": "fixture-command",
                        "type": "commandExecution",
                        "command": "printf fixture",
                        "commandActions": [],
                        "cwd": "/workspace",
                        "status": "declined",
                    },
                },
            }
        )
        self.send(
            {
                "method": "error",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "error": {"message": "Fixture approval was declined"},
                },
            }
        )
        self._complete_turn("failed", error="Fixture approval was declined")

    def _complete_turn(self, status: str, error: str | None = None) -> None:
        turn: dict[str, Any] = {"id": self.turn_id, "items": [], "status": status}
        if error:
            turn["error"] = {"message": error}
        self.send(
            {
                "method": "turn/completed",
                "params": {"threadId": self.thread_id, "turn": turn},
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=("basic", "reject", "tool-failure", "cancel", "malformed"),
        default="basic",
    )
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    FakeAppServer(args.scenario, args.log).run()


if __name__ == "__main__":
    main()
