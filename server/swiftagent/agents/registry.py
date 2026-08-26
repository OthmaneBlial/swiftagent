"""Validated registry of available coding-agent adapter factories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from swiftagent.agents.base import AgentAdapter
from swiftagent.models.agent import AgentCapabilities, AgentDefinition
from swiftagent.models.task import Task

AdapterFactory = Callable[[Task, Any], AgentAdapter]


class AgentRegistry:
    """Maps stable agent IDs to metadata and adapter factories."""

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, definition: AgentDefinition, factory: AdapterFactory) -> None:
        if definition.agent_id in self._definitions:
            raise ValueError(f"Agent is already registered: {definition.agent_id}")
        self._definitions[definition.agent_id] = definition
        self._factories[definition.agent_id] = factory

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


def _create_claude_adapter(task: Task, manager: Any) -> AgentAdapter:
    # Lazy import keeps the registry independent from concrete adapter modules.
    from swiftagent.engine.adapter import ClaudeAdapter

    return ClaudeAdapter(task, manager)


agent_registry = AgentRegistry()
agent_registry.register(
    AgentDefinition(
        agent_id="claude-code",
        display_name="Claude Code",
        adapter_id="claude-stream-json",
        adapter_version="0.3.0",
        protocol="stream-json",
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
)
