"""Deterministic ACP v1 subprocess used by SwiftAgent's contract tests."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from acp import (
    RequestError,
    plan_entry,
    run_agent,
    start_tool_call,
    update_agent_message_text,
    update_agent_thought_text,
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


class FakeAgent:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.client: Any = None
        self.cwd: Path | None = None
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
                promptCapabilities=PromptCapabilities(),
                sessionCapabilities=SessionCapabilities(resume=SessionResumeCapabilities()),
            ),
            authMethods=[],
            agentInfo=Implementation(name="swiftagent-fixture", title="ACP Fixture", version="1.0.0"),
        )

    async def authenticate(self, method_id: str, **_kwargs: Any) -> AuthenticateResponse:
        raise RequestError.invalid_params({"details": f"unexpected auth method: {method_id}"})

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> NewSessionResponse:
        self.cwd = Path(cwd)
        return NewSessionResponse(sessionId="fake-acp-session")

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        additional_directories: list[str] | None = None,
        **_kwargs: Any,
    ) -> LoadSessionResponse:
        if session_id != "fake-acp-session":
            raise RequestError.invalid_params({"details": "unknown fixture session"})
        self.cwd = Path(cwd)
        return LoadSessionResponse()

    async def prompt(self, session_id: str, prompt: list[Any], **_kwargs: Any) -> PromptResponse:
        if self.cwd is None or session_id != "fake-acp-session":
            raise RequestError.invalid_params({"details": "fixture session is not initialized"})
        if self.scenario == "cancel":
            await self.cancelled.wait()
            return PromptResponse(stopReason="cancelled")

        await self.client.session_update(session_id, update_agent_thought_text("private fixture thought"))
        await self.client.session_update(
            session_id,
            start_tool_call(
                "fixture-read",
                "Read fixture input",
                kind="read",
                status="in_progress",
                raw_input={"path": str(self.cwd / "fixture-input.txt")},
            ),
        )
        read_response = await self.client.read_text_file(
            session_id, str(self.cwd / "fixture-input.txt")
        )
        permission = await self.client.request_permission(
            session_id,
            ToolCallUpdate(
                toolCallId="fixture-write",
                title="Write fixture output",
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
                f"ACP copied: {read_response.content.strip()}\n",
            )
        await self.client.session_update(
            session_id,
            update_tool_call(
                "fixture-read",
                title="Read fixture input",
                kind="read",
                status="completed",
                raw_output={"chars": len(read_response.content)},
            ),
        )
        terminal = await self.client.create_terminal(
            session_id,
            sys.executable,
            ["-c", "print('terminal:' + 'x' * 80)"],
            cwd=str(self.cwd),
            output_byte_limit=32,
        )
        terminal_result = await self.client.wait_for_terminal_exit(
            session_id, terminal.terminal_id
        )
        terminal_output = await self.client.terminal_output(session_id, terminal.terminal_id)
        await self.client.release_terminal(session_id, terminal.terminal_id)
        await self.client.session_update(
            session_id,
            update_plan([plan_entry("Exercise ACP callbacks", status="completed")]),
        )
        await self.client.session_update(
            session_id,
            UsageUpdate(sessionUpdate="usage_update", used=17, size=128),
        )
        await self.client.session_update(
            session_id,
            update_agent_message_text(
                "ACP fixture completed. "
                f"terminal_exit={terminal_result.exit_code}; truncated={terminal_output.truncated}."
            ),
        )
        return PromptResponse(stopReason="end_turn")

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        if session_id == "fake-acp-session":
            self.cancelled.set()

    async def set_session_mode(self, session_id: str, mode_id: str, **_kwargs: Any) -> None:
        return None

    async def set_config_option(
        self, config_id: str, session_id: str, value: str | bool, **_kwargs: Any
    ) -> None:
        return None

    async def ext_method(self, method: str, _params: dict[str, Any]) -> dict[str, Any]:
        raise RequestError.method_not_found(f"_{method}")

    async def ext_notification(self, _method: str, _params: dict[str, Any]) -> None:
        return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("basic", "cancel"), default="basic")
    args = parser.parse_args()
    await run_agent(FakeAgent(args.scenario))


if __name__ == "__main__":
    asyncio.run(main())
