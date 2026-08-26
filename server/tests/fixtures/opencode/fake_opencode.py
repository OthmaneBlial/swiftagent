#!/usr/bin/env python3
"""Deterministic OpenCode CLI/ACP/JSON fixture; never performs inference."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

for site_packages in (Path(__file__).resolve().parents[3] / ".venv" / "lib").glob(
    "python*/site-packages"
):
    sys.path.insert(0, str(site_packages))

from acp import (  # noqa: E402
    RequestError,
    plan_entry,
    run_agent,
    start_tool_call,
    update_agent_message_text,
    update_plan,
    update_tool_call,
)
from acp.schema import (  # noqa: E402
    AgentCapabilities,
    AuthenticateResponse,
    Implementation,
    InitializeResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PermissionOption,
    PromptCapabilities,
    PromptResponse,
    SessionCapabilities,
    SessionConfigOptionSelect,
    SessionConfigSelectOption,
    SessionForkCapabilities,
    SessionResumeCapabilities,
    SetSessionConfigOptionResponse,
    ToolCallUpdate,
    UsageUpdate,
)

MODELS = ["fixture/free-model", "fixture/second-model"]
SESSION_ID = "fake-opencode-session"


def _record(payload: dict[str, Any]) -> None:
    target = os.environ.get("SWIFTAGENT_TEST_OPENCODE_LOG")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _model_option(current: str = MODELS[0]) -> SessionConfigOptionSelect:
    return SessionConfigOptionSelect(
        type="select",
        id="model",
        name="Model",
        category="model",
        currentValue=current,
        options=[SessionConfigSelectOption(value=model, name=model) for model in MODELS],
    )


class FakeOpenCodeAgent:
    def __init__(self) -> None:
        self.client: Any = None
        self.cwd: Path | None = None
        self.model = MODELS[0]
        self.cancelled = asyncio.Event()

    def on_connect(self, client: Any) -> None:
        self.client = client

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any = None,
        client_info: Any = None,
        **_kwargs: Any,
    ) -> InitializeResponse:
        if protocol_version != 1:
            raise RequestError.invalid_params({"details": "fixture supports ACP v1 only"})
        return InitializeResponse(
            protocolVersion=1,
            agentCapabilities=AgentCapabilities(
                loadSession=True,
                promptCapabilities=PromptCapabilities(image=True, embeddedContext=True),
                sessionCapabilities=SessionCapabilities(
                    resume=SessionResumeCapabilities(),
                    fork=SessionForkCapabilities(),
                ),
            ),
            authMethods=[],
            agentInfo=Implementation(name="OpenCode", version="1.18.13"),
        )

    async def authenticate(self, method_id: str, **_kwargs: Any) -> AuthenticateResponse:
        raise RequestError.invalid_params({"details": f"unexpected auth method: {method_id}"})

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> NewSessionResponse:
        self.cwd = Path(cwd)
        return NewSessionResponse(sessionId=SESSION_ID, configOptions=[_model_option(self.model)])

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> LoadSessionResponse:
        if session_id != SESSION_ID:
            raise RequestError.invalid_params({"details": "unknown fixture session"})
        self.cwd = Path(cwd)
        return LoadSessionResponse(configOptions=[_model_option(self.model)])

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str | bool,
        **_kwargs: Any,
    ) -> SetSessionConfigOptionResponse:
        if config_id != "model" or session_id != SESSION_ID or value not in MODELS:
            raise RequestError.invalid_params({"details": "invalid fixture model selection"})
        self.model = str(value)
        _record({"method": "set_config_option", "model": self.model})
        return SetSessionConfigOptionResponse(configOptions=[_model_option(self.model)])

    async def prompt(self, session_id: str, prompt: list[Any], **_kwargs: Any) -> PromptResponse:
        if session_id != SESSION_ID or self.cwd is None:
            raise RequestError.invalid_params({"details": "fixture session is not initialized"})
        prompt_text = "".join(
            str(getattr(block, "text", "")) for block in prompt
        )
        _record({"method": "prompt", "prompt": prompt_text})
        if os.environ.get("SWIFTAGENT_TEST_OPENCODE_SCENARIO") == "cancel":
            await self.cancelled.wait()
            return PromptResponse(stopReason="cancelled")

        await self.client.session_update(
            session_id,
            start_tool_call(
                "opencode-write",
                "Write OpenCode fixture",
                kind="edit",
                status="pending",
                raw_input={"path": str(self.cwd / "opencode-output.txt")},
            ),
        )
        permission = await self.client.request_permission(
            session_id,
            ToolCallUpdate(
                toolCallId="opencode-write",
                title="Write OpenCode fixture",
                kind="edit",
                status="pending",
            ),
            [
                PermissionOption(optionId="once", name="Allow once", kind="allow_once"),
                PermissionOption(optionId="reject", name="Reject", kind="reject_once"),
            ],
        )
        if getattr(permission.outcome, "outcome", None) == "selected":
            await self.client.write_text_file(
                session_id,
                str(self.cwd / "opencode-output.txt"),
                f"model={self.model}\n",
            )
        await self.client.session_update(
            session_id,
            update_tool_call(
                "opencode-write",
                title="Write OpenCode fixture",
                kind="edit",
                status="completed",
                raw_output={"model": self.model},
            ),
        )
        await self.client.session_update(
            session_id,
            update_plan([plan_entry("Exercise OpenCode ACP", status="completed")]),
        )
        await self.client.session_update(
            session_id,
            UsageUpdate(sessionUpdate="usage_update", used=11, size=64),
        )
        await self.client.session_update(
            session_id,
            update_agent_message_text(f"OpenCode ACP fixture completed with {self.model}."),
        )
        return PromptResponse(stopReason="end_turn")

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        if session_id == SESSION_ID:
            self.cancelled.set()

    async def set_session_mode(self, session_id: str, mode_id: str, **_kwargs: Any) -> None:
        return None

    async def ext_method(self, method: str, _params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(method)

    async def ext_notification(self, _method: str, _params: dict[str, Any]) -> None:
        return None


def _json_event(event: dict[str, Any]) -> None:
    print(json.dumps(event, separators=(",", ":")), flush=True)


async def _run_json_fallback(args: list[str]) -> None:
    scenario = os.environ.get("SWIFTAGENT_TEST_OPENCODE_SCENARIO", "basic")
    session_id = SESSION_ID
    if "--session" in args:
        session_id = args[args.index("--session") + 1]
    model = args[args.index("--model") + 1] if "--model" in args else MODELS[0]
    if scenario == "malformed":
        print("{not-json", flush=True)
        return
    _json_event(
        {
            "type": "step_start",
            "sessionID": session_id,
            "part": {"id": "step-1", "type": "step-start"},
        }
    )
    if scenario == "cancel":
        await asyncio.sleep(60)
        return
    _json_event(
        {
            "type": "tool_use",
            "sessionID": session_id,
            "part": {
                "id": "tool-1",
                "tool": "read",
                "state": {"status": "running", "input": {"path": "fixture.txt"}},
            },
        }
    )
    _json_event(
        {
            "type": "tool_use",
            "sessionID": session_id,
            "part": {
                "id": "tool-1",
                "tool": "read",
                "state": {"status": "completed", "output": "fixture"},
            },
        }
    )
    _json_event(
        {
            "type": "text",
            "sessionID": session_id,
            "part": {"id": "text-1", "type": "text", "text": f"OpenCode JSON {model}."},
        }
    )
    _json_event(
        {
            "type": "step_finish",
            "sessionID": session_id,
            "part": {
                "type": "step-finish",
                "reason": "stop",
                "tokens": {"input": 7, "output": 4, "reasoning": 0},
                "cost": 0,
            },
        }
    )


def main() -> None:
    args = sys.argv[1:]
    _record({"method": "argv", "args": args, "cwd": os.getcwd()})
    if args == ["--version"]:
        print("1.18.13")
        return
    if args and args[0] == "models":
        print("\n".join(MODELS))
        return
    if args[:2] == ["acp", "--help"]:
        if os.environ.get("SWIFTAGENT_TEST_OPENCODE_NO_ACP") == "1":
            raise SystemExit(2)
        print("start ACP (Agent Client Protocol) server")
        return
    if args and args[0] == "acp":
        if os.environ.get("SWIFTAGENT_TEST_OPENCODE_NO_ACP") == "1":
            raise SystemExit(2)
        asyncio.run(run_agent(FakeOpenCodeAgent()))
        return
    if args[:2] == ["run", "--help"]:
        print("--format format: default or json")
        return
    if args and args[0] == "run":
        asyncio.run(_run_json_fallback(args))
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
