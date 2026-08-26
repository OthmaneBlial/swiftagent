"""Validated registry of available coding-agent adapter factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swiftagent.agents.base import AgentAdapter
from swiftagent.models.agent import AgentCapabilities, AgentDefinition, AgentStatus
from swiftagent.models.task import Task

AdapterFactory = Callable[[Task, Any], AgentAdapter]
StatusProvider = Callable[[AgentDefinition], AgentStatus]


class AgentRegistry:
    """Maps stable agent IDs to metadata and adapter factories."""

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        self._factories: dict[str, AdapterFactory] = {}
        self._status_providers: dict[str, StatusProvider] = {}
        self._status_cache: dict[str, AgentStatus] = {}

    def register(
        self,
        definition: AgentDefinition,
        factory: AdapterFactory,
        status_provider: StatusProvider | None = None,
    ) -> None:
        if definition.agent_id in self._definitions:
            raise ValueError(f"Agent is already registered: {definition.agent_id}")
        self._definitions[definition.agent_id] = definition
        self._factories[definition.agent_id] = factory
        if status_provider:
            self._status_providers[definition.agent_id] = status_provider

    def definition(self, agent_id: str) -> AgentDefinition:
        try:
            return self._definitions[agent_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._definitions)) or "none"
            raise ValueError(f"Unknown agent '{agent_id}'. Available agents: {available}") from exc

    def create(self, agent_id: str, task: Task, manager: Any) -> AgentAdapter:
        self.definition(agent_id)
        return self._factories[agent_id](task, manager)

    def definitions(self) -> list[AgentDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]

    def statuses(self, *, refresh: bool = False) -> list[AgentStatus]:
        statuses: list[AgentStatus] = []
        for definition in self.definitions():
            provider = self._status_providers.get(definition.agent_id)
            if not refresh and definition.agent_id in self._status_cache:
                statuses.append(self._status_cache[definition.agent_id])
                continue
            if provider:
                status = provider(definition)
                self._status_cache[definition.agent_id] = status
                statuses.append(status)
                continue
            status = AgentStatus(
                **definition.model_dump(),
                installed=True,
                compatible=None,
                detail="No discovery probe is registered for this adapter.",
            )
            self._status_cache[definition.agent_id] = status
            statuses.append(status)
        return statuses


def _create_claude_adapter(task: Task, manager: Any) -> AgentAdapter:
    # Lazy import keeps the registry independent from concrete adapter modules.
    from swiftagent.agents.claude import ClaudeCodeAdapter

    return ClaudeCodeAdapter(task, manager)


def _get_claude_status(definition: AgentDefinition) -> AgentStatus:
    from swiftagent.agents.claude.status import get_status

    return get_status(definition)


def _create_acp_adapter(task: Task, manager: Any) -> AgentAdapter:
    from swiftagent.agents.acp import AcpAdapter

    return AcpAdapter(task, manager)


def _get_acp_status(definition: AgentDefinition) -> AgentStatus:
    from swiftagent.agents.acp.status import get_status

    return get_status(definition)


def _create_codex_adapter(task: Task, manager: Any) -> AgentAdapter:
    from swiftagent.agents.codex import CodexAdapter

    return CodexAdapter(task, manager)


def _get_codex_status(definition: AgentDefinition) -> AgentStatus:
    from swiftagent.agents.codex.status import get_status

    return get_status(definition)


agent_registry = AgentRegistry()
agent_registry.register(
    AgentDefinition(
        agent_id="claude-code",
        display_name="Claude Code",
        adapter_id="claude-stream-json",
        adapter_version="0.3.0",
        protocol="stream-json",
        install_url="https://docs.anthropic.com/en/docs/claude-code/setup",
        documentation_url="https://docs.anthropic.com/en/docs/claude-code/overview",
        capabilities=AgentCapabilities(
            structured_streaming=True,
            session_resume=True,
            tool_events=True,
            approvals=False,
            questions=False,
            model_discovery=False,
            mode_discovery=False,
            native_sandbox=False,
            external_sandbox="partial",
        ),
    ),
    _create_claude_adapter,
    _get_claude_status,
)
agent_registry.register(
    AgentDefinition(
        agent_id="acp-agent",
        display_name="ACP Agent",
        adapter_id="acp-v1",
        adapter_version="0.4.0",
        protocol="acp-v1",
        install_url="https://agentclientprotocol.com/get-started/introduction",
        documentation_url="https://agentclientprotocol.com/protocol/overview",
        capabilities=AgentCapabilities(
            structured_streaming=True,
            session_resume=False,
            tool_events=True,
            approvals=True,
            questions=False,
            plan_updates=True,
            usage=True,
            external_sandbox="partial",
        ),
    ),
    _create_acp_adapter,
    _get_acp_status,
)
agent_registry.register(
    AgentDefinition(
        agent_id="codex",
        display_name="Codex",
        adapter_id="codex-app-server-v2",
        adapter_version="0.4.0",
        protocol="codex-app-server-v2",
        install_url="https://learn.chatgpt.com/docs/codex-cli",
        documentation_url="https://learn.chatgpt.com/docs/app-server",
        capabilities=AgentCapabilities(
            structured_streaming=True,
            session_resume=True,
            session_fork=True,
            tool_events=True,
            approvals=True,
            questions=True,
            plan_updates=True,
            attachments=True,
            attachment_types=["image/*"],
            model_discovery=True,
            usage=True,
            native_sandbox=True,
            external_sandbox="partial",
        ),
    ),
    _create_codex_adapter,
    _get_codex_status,
)
