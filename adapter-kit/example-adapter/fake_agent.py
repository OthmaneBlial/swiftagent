"""Minimal deterministic ACP v1 agent for the public SwiftAgent adapter kit."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from acp import (
    RequestError,
    plan_entry,
    run_agent,
    start_tool_call,
    update_agent_message_text,
    update_plan,
    update_tool_call,
)
from acp.schema import (
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
    SessionResumeCapabilities,
    ToolCallUpdate,
    UsageUpdate,
)


class ExampleAgent:
    """Small ACP agent that exercises files, approval, plan, usage, and resume."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.client: Any = None
        self.cwd: Path | None = None
        self.cancelled = asyncio.Event()

    def on_connect(self, client: Any) -> None:
        self.client = client

    async def initialize(self, protocol_version: int, **_kwargs: Any) -> InitializeResponse:
        if protocol_version != 1:
            raise RequestError.invalid_params({"details": "example agent supports ACP v1 only"})
        return InitializeResponse(
            protocolVersion=1,
            agentCapabilities=AgentCapabilities(
                loadSession=True,
                promptCapabilities=PromptCapabilities(),
                sessionCapabilities=SessionCapabilities(
                    resume=SessionResumeCapabilities()
                ),
            ),
            authMethods=[],
            agentInfo=Implementation(
                name="swiftagent-example-acp",
                title="SwiftAgent example ACP agent",
                version="1.0.0",
            ),
        )

    async def authenticate(self, method_id: str, **_kwargs: Any) -> AuthenticateResponse:
        raise RequestError.invalid_params({"details": f"unexpected auth method: {method_id}"})

    async def new_session(self, cwd: str, **_kwargs: Any) -> NewSessionResponse:
        self.cwd = Path(cwd)
        return NewSessionResponse(sessionId="swiftagent-example-session")

    async def load_session(self, cwd: str, session_id: str, **_kwargs: Any) -> LoadSessionResponse:
        if session_id != "swiftagent-example-session":
            raise RequestError.invalid_params({"details": "unknown example session"})
        self.cwd = Path(cwd)
        return LoadSessionResponse()

    async def prompt(self, session_id: str, prompt: list[Any], **_kwargs: Any) -> PromptResponse:
        if self.cwd is None or session_id != "swiftagent-example-session":
            raise RequestError.invalid_params({"details": "example session is not initialized"})
        if self.scenario == "cancel":
            await self.cancelled.wait()
            return PromptResponse(stopReason="cancelled")

        await self.client.session_update(
            session_id,
            start_tool_call(
                "example-read",
                "Read contract fixture",
                kind="read",
                status="in_progress",
                raw_input={"path": str(self.cwd / "fixture-input.txt")},
            ),
        )
        source = await self.client.read_text_file(
            session_id, str(self.cwd / "fixture-input.txt")
        )
        permission = await self.client.request_permission(
            session_id,
            ToolCallUpdate(
                toolCallId="example-write",
                title="Write bounded contract output",
                kind="edit",
                status="pending",
            ),
            [
                PermissionOption(optionId="allow", name="Allow once", kind="allow_once"),
                PermissionOption(optionId="reject", name="Reject", kind="reject_once"),
            ],
        )
        if getattr(permission.outcome, "outcome", None) == "selected":
            await self.client.write_text_file(
                session_id,
                str(self.cwd / "fixture-output.txt"),
                f"Example ACP copied: {source.content.strip()}\n",
            )
        await self.client.session_update(
            session_id,
            update_tool_call(
                "example-read",
                title="Read contract fixture",
                kind="read",
                status="completed",
                raw_output={"chars": len(source.content)},
            ),
        )
        await self.client.session_update(
            session_id,
            update_plan([plan_entry("Exercise adapter contract", status="completed")]),
        )
        await self.client.session_update(
            session_id,
            UsageUpdate(sessionUpdate="usage_update", used=8, size=64),
        )
        await self.client.session_update(
            session_id,
            update_agent_message_text("Example ACP adapter contract completed."),
        )
        return PromptResponse(stopReason="end_turn")

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        if session_id == "swiftagent-example-session":
            self.cancelled.set()

    async def set_session_mode(self, **_kwargs: Any) -> None:
        return None

    async def set_config_option(self, **_kwargs: Any) -> None:
        return None

    async def ext_method(self, method: str, _params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(f"_{method}")

    async def ext_notification(self, _method: str, _params: dict[str, Any]) -> None:
        return None


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="example-acp-agent 1.0.0")
    parser.add_argument("--scenario", choices=("basic", "cancel"), default="basic")
    arguments = parser.parse_args()
    await run_agent(ExampleAgent(arguments.scenario))


if __name__ == "__main__":
    asyncio.run(run())
