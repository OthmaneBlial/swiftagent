from __future__ import annotations

from pathlib import Path

import pytest

from swiftagent.agents.claude import ClaudeCodeAdapter
from swiftagent.agents.claude.parser import MessageType, ParsedMessage, StreamParser
from swiftagent.models.agent import AgentEventType
from swiftagent.models.task import Task, TaskConfig, TaskStatus
from swiftagent.storage import tasks as task_repo

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "claude_stream"


def _parse_fixture(name: str, *, chunk_size: int | None = None) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    parser = StreamParser(messages.append)
    payload = (FIXTURE_DIR / name).read_text(encoding="utf-8")

    if chunk_size is None:
        parser.feed(payload)
    else:
        for offset in range(0, len(payload), chunk_size):
            parser.feed(payload[offset : offset + chunk_size])

    parser.flush()
    return messages


def test_successful_stream_contract_preserves_session_tools_and_result():
    messages = _parse_fixture("successful_run.jsonl")

    assert [message.type for message in messages] == [
        MessageType.SESSION_ID,
        MessageType.TEXT,
        MessageType.TOOL_USE,
        MessageType.TOOL_RESULT,
        MessageType.TEXT,
        MessageType.RESULT,
        MessageType.SESSION_ID,
    ]
    assert messages[0].content == "fixture-session-001"
    assert messages[2].data["tool_use_id"] == "toolu_fixture_001"
    assert messages[2].data["name"] == "Read"
    assert messages[2].data["input"] == {"file_path": "README.md"}
    assert messages[3].content == "# Fixture project"
    assert messages[3].data["is_error"] is False
    assert messages[5].data["success"] is True
    assert messages[5].data["result"] == "Inspection completed."


def test_stream_parser_handles_fragmented_and_malformed_input():
    messages = _parse_fixture("malformed_run.jsonl", chunk_size=7)

    assert [message.type for message in messages] == [MessageType.TEXT, MessageType.ERROR]
    assert messages[0].content == "A plain string content block is accepted."
    assert messages[1].content == "Synthetic top-level stream error"


def test_failed_stream_contract_is_terminal_and_resumable():
    messages = _parse_fixture("failed_run.jsonl", chunk_size=13)
    result = next(message for message in messages if message.type is MessageType.RESULT)

    assert result.data["success"] is False
    assert result.data["error"] == "Permission denied by fixture policy."
    assert result.data["session_id"] == "fixture-session-failed"
    assert messages[-1].type is MessageType.SESSION_ID


def test_claude_argument_contract_for_new_and_resumed_runs(monkeypatch):
    import swiftagent.agents.claude.settings as claude_settings

    monkeypatch.setattr(claude_settings, "get_model", lambda: "default-model")
    monkeypatch.setattr(
        claude_settings,
        "get_permission_mode",
        lambda: "plan",
    )

    fresh = ClaudeCodeAdapter(
        Task(config=TaskConfig(prompt="Inspect this repository", model_id="task-model")),
        manager=None,  # type: ignore[arg-type]
    )
    assert fresh._build_claude_args() == [
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--model",
        "task-model",
        "--permission-mode",
        "plan",
        "Inspect this repository",
    ]

    resumed = ClaudeCodeAdapter(
        Task(
            config=TaskConfig(prompt="Continue the review"),
            session_id="fixture-session-001",
        ),
        manager=None,  # type: ignore[arg-type]
    )
    assert resumed._build_claude_args() == [
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--model",
        "default-model",
        "--permission-mode",
        "plan",
        "-r",
        "fixture-session-001",
        "Continue the review",
    ]


def test_fallback_command_is_an_argument_array_with_an_explicit_warning(monkeypatch, tmp_path):
    import swiftagent.agents.claude.settings as claude_settings
    import swiftagent.storage.settings as app_settings

    monkeypatch.setattr(app_settings, "get_sandbox_mode", lambda: "fallback")
    monkeypatch.setattr(claude_settings, "get_model", lambda: None)
    monkeypatch.setattr(
        claude_settings,
        "get_permission_mode",
        lambda: "default",
    )
    adapter = ClaudeCodeAdapter(
        Task(config=TaskConfig(prompt="Read only")),
        manager=None,  # type: ignore[arg-type]
    )

    command, warning = adapter._build_command("/usr/local/bin/claude", tmp_path)

    assert command[0] == "/usr/local/bin/claude"
    assert command[-1] == "Read only"
    assert "not OS-isolated" in (warning or "")


def test_engine_status_contract_exposes_cli_and_strict_sandbox_state(client, monkeypatch):
    import swiftagent.agents.claude.status as status_module

    monkeypatch.setattr(status_module, "resolve_cli_path", lambda: "/opt/tools/claude")
    monkeypatch.setattr(
        status_module.shutil,
        "which",
        lambda executable: "/usr/bin/bwrap" if executable == "bwrap" else None,
    )
    monkeypatch.setattr(
        status_module,
        "check_bwrap_usable",
        lambda _workspace: (True, None),
    )
    monkeypatch.setattr(status_module.settings_repo, "get_sandbox_mode", lambda: "strict")

    response = client.get("/api/engine/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["claude_cli_available"] is True
    assert payload["claude_cli_path"] == "/opt/tools/claude"
    assert payload["bwrap_available"] is True
    assert payload["bwrap_usable"] is True
    assert payload["strict_sandbox_active"] is True
    assert payload["degraded"] is False


@pytest.mark.asyncio
async def test_claude_adapter_maps_native_messages_to_bounded_normalized_events(client):
    class RecordingManager:
        def __init__(self):
            self.legacy = []
            self.normalized = []

        async def broadcast(self, event):
            self.legacy.append(event)

        async def broadcast_agent_event(self, event):
            self.normalized.append(event)

    task = Task(config=TaskConfig(prompt="Inspect this repository"), status=TaskStatus.RUNNING)
    task_repo.save_task(task)
    manager = RecordingManager()
    adapter = ClaudeCodeAdapter(task, manager)  # type: ignore[arg-type]
    messages = _parse_fixture("successful_run.jsonl")

    for message in messages:
        await adapter._handle_message_async(message)

    event_types = [event.type for event in manager.normalized]
    assert event_types == [
        AgentEventType.MESSAGE_COMPLETED,
        AgentEventType.TOOL_STARTED,
        AgentEventType.TOOL_COMPLETED,
        AgentEventType.MESSAGE_COMPLETED,
        AgentEventType.RUN_COMPLETED,
    ]
    assert all(event.agent_id == "claude-code" for event in manager.normalized)
    assert all(event.adapter_id == "claude-stream-json" for event in manager.normalized)
    assert manager.normalized[-1].native_session_id == "fixture-session-001"
    assert manager.normalized[1].native_metadata["type"] == "assistant"
    assert task.status is TaskStatus.COMPLETED
    assert task_repo.get_task(task.id).native_session_id == "fixture-session-001"  # type: ignore[union-attr]


def test_native_diagnostics_are_bounded():
    message = ParsedMessage(
        type=MessageType.TEXT,
        content="ok",
        data={"raw": {"type": "assistant", "large": "x" * 20_000}},
    )

    metadata = ClaudeCodeAdapter._native_metadata(message, max_chars=100)

    assert metadata["truncated"] is True
    assert len(metadata["preview"]) == 100
