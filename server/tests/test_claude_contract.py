from __future__ import annotations

from pathlib import Path

from swiftagent.engine.adapter import ClaudeAdapter
from swiftagent.engine.parser import MessageType, ParsedMessage, StreamParser
from swiftagent.models.task import Task, TaskConfig

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
    import swiftagent.engine.adapter as adapter_module

    monkeypatch.setattr(adapter_module.settings_repo, "get_claude_model", lambda: "default-model")
    monkeypatch.setattr(
        adapter_module.settings_repo,
        "get_claude_permission_mode",
        lambda: "plan",
    )

    fresh = ClaudeAdapter(
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

    resumed = ClaudeAdapter(
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
    import swiftagent.engine.adapter as adapter_module

    monkeypatch.setattr(adapter_module.settings_repo, "get_sandbox_mode", lambda: "fallback")
    monkeypatch.setattr(adapter_module.settings_repo, "get_claude_model", lambda: None)
    monkeypatch.setattr(
        adapter_module.settings_repo,
        "get_claude_permission_mode",
        lambda: "default",
    )
    adapter = ClaudeAdapter(
        Task(config=TaskConfig(prompt="Read only")),
        manager=None,  # type: ignore[arg-type]
    )

    command, warning = adapter._build_command("/usr/local/bin/claude", tmp_path)

    assert command[0] == "/usr/local/bin/claude"
    assert command[-1] == "Read only"
    assert "not OS-isolated" in (warning or "")


def test_engine_status_contract_exposes_cli_and_strict_sandbox_state(client, monkeypatch):
    import swiftagent.api.routes as routes_module

    monkeypatch.setattr(routes_module, "_resolve_claude_path", lambda: "/opt/tools/claude")
    monkeypatch.setattr(
        routes_module.shutil,
        "which",
        lambda executable: "/usr/bin/bwrap" if executable == "bwrap" else None,
    )
    monkeypatch.setattr(
        routes_module,
        "check_bwrap_usable",
        lambda _workspace: (True, None),
    )
    monkeypatch.setattr(routes_module.settings_repo, "get_sandbox_mode", lambda: "strict")

    response = client.get("/api/engine/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["claude_cli_available"] is True
    assert payload["claude_cli_path"] == "/opt/tools/claude"
    assert payload["bwrap_available"] is True
    assert payload["bwrap_usable"] is True
    assert payload["strict_sandbox_active"] is True
    assert payload["degraded"] is False
