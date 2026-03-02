"""
Stream parser — parses OpenCode CLI stdout into structured messages.

Ported from base/accomplish/packages/agent-core/src/internal/classes/StreamParser.ts
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class MessageType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STEP_FINISH = "step_finish"
    ERROR = "error"
    SESSION_ID = "session_id"
    COMPLETE = "complete"
    PERMISSION = "permission"
    THOUGHT = "thought"
    REASONING = "reasoning"
    TODO = "todo"


@dataclass
class ParsedMessage:
    type: MessageType
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class StreamParser:
    """
    Parses newline-delimited JSON (NDJSON) from OpenCode CLI output
    into structured ParsedMessage objects.
    """

    def __init__(self, on_message: Callable[[ParsedMessage], None]):
        self._on_message = on_message
        self._buffer = ""

    def feed(self, chunk: str) -> None:
        """Feed raw output data into the parser."""
        self._buffer += chunk

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            self._parse_line(line)

    def flush(self) -> None:
        """Flush any remaining buffer content."""
        if self._buffer.strip():
            self._parse_line(self._buffer.strip())
            self._buffer = ""

    def _parse_line(self, line: str) -> None:
        """Parse a single line of output."""
        # Try JSON first (OpenCode structured output)
        if line.startswith("{"):
            try:
                data = json.loads(line)
                msg = self._parse_json_message(data)
                if msg:
                    self._on_message(msg)
                    return
            except json.JSONDecodeError:
                pass

        # Fall back to plain text
        self._on_message(ParsedMessage(type=MessageType.TEXT, content=line))

    def _parse_json_message(self, data: dict) -> ParsedMessage | None:
        """Parse a JSON message from OpenCode CLI."""
        msg_type = data.get("type", "")

        if msg_type == "text" or msg_type == "content":
            return ParsedMessage(
                type=MessageType.TEXT,
                content=data.get("content", data.get("text", "")),
                data=data,
            )

        if msg_type == "tool_call" or msg_type == "tool-call":
            return ParsedMessage(
                type=MessageType.TOOL_CALL,
                content=data.get("name", ""),
                data=data,
            )

        if msg_type == "tool_result" or msg_type == "tool-result":
            return ParsedMessage(
                type=MessageType.TOOL_RESULT,
                content=data.get("content", ""),
                data=data,
            )

        if msg_type == "step_finish" or msg_type == "step-finish":
            return ParsedMessage(
                type=MessageType.STEP_FINISH,
                data=data,
            )

        if msg_type == "error":
            return ParsedMessage(
                type=MessageType.ERROR,
                content=data.get("message", data.get("error", "")),
                data=data,
            )

        if msg_type == "session":
            return ParsedMessage(
                type=MessageType.SESSION_ID,
                content=data.get("sessionId", data.get("session_id", "")),
                data=data,
            )

        if msg_type == "complete" or msg_type == "done":
            return ParsedMessage(
                type=MessageType.COMPLETE,
                data=data,
            )

        if msg_type == "thought":
            return ParsedMessage(
                type=MessageType.THOUGHT,
                content=data.get("content", ""),
                data=data,
            )

        if msg_type == "reasoning":
            return ParsedMessage(
                type=MessageType.REASONING,
                content=data.get("content", ""),
                data=data,
            )

        if msg_type == "todo" or msg_type == "todos":
            return ParsedMessage(
                type=MessageType.TODO,
                data=data,
            )

        # Unknown type — still forward it
        return ParsedMessage(
            type=MessageType.TEXT,
            content=json.dumps(data),
            data=data,
        )
