"""Stream parser for Claude CLI ``stream-json`` output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class MessageType(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SESSION_ID = "session_id"
    RESULT = "result"
    ERROR = "error"


@dataclass
class ParsedMessage:
    type: MessageType
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class StreamParser:
    """Parses line-delimited JSON events emitted by Claude CLI."""

    def __init__(self, on_message: Callable[[ParsedMessage], None]):
        self._on_message = on_message
        self._buffer = ""

    def feed(self, chunk: str) -> None:
        self._buffer += chunk

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._parse_line(line.strip())

    def flush(self) -> None:
        if self._buffer.strip():
            self._parse_line(self._buffer.strip())
        self._buffer = ""

    def _parse_line(self, line: str) -> None:
        if not line:
            return

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        event_type = payload.get("type")

        if event_type == "system":
            session_id = payload.get("session_id")
            if session_id:
                self._on_message(
                    ParsedMessage(type=MessageType.SESSION_ID, content=session_id, data=payload)
                )
            return

        if event_type == "assistant":
            message = payload.get("message") or {}
            content_parts = message.get("content") or []
            if isinstance(content_parts, str):
                content_parts = [{"type": "text", "text": content_parts}]
            for part in content_parts:
                part_type = part.get("type")
                if part_type == "text":
                    text = str(part.get("text") or "")
                    if text:
                        self._on_message(
                            ParsedMessage(type=MessageType.TEXT, content=text, data=payload)
                        )
                elif part_type == "tool_use":
                    self._on_message(
                        ParsedMessage(
                            type=MessageType.TOOL_USE,
                            content=str(part.get("name") or "unknown"),
                            data={
                                "tool_use_id": part.get("id"),
                                "name": part.get("name"),
                                "input": part.get("input") or {},
                                "raw": payload,
                            },
                        )
                    )
            return

        if event_type == "user":
            message = payload.get("message") or {}
            content_parts = message.get("content") or []
            if isinstance(content_parts, str):
                content_parts = [{"type": "text", "text": content_parts}]
            for part in content_parts:
                if part.get("type") != "tool_result":
                    continue
                content = part.get("content")
                if isinstance(content, list):
                    flattened = []
                    for item in content:
                        if isinstance(item, str):
                            flattened.append(item)
                        elif isinstance(item, dict):
                            flattened.append(str(item.get("text") or ""))
                    text_content = "\n".join(v for v in flattened if v).strip()
                else:
                    text_content = str(content or "")

                self._on_message(
                    ParsedMessage(
                        type=MessageType.TOOL_RESULT,
                        content=text_content,
                        data={
                            "tool_use_id": part.get("tool_use_id"),
                            "is_error": bool(part.get("is_error")),
                            "raw": payload,
                        },
                    )
                )
            return

        if event_type == "result":
            result_text = str(payload.get("result") or "")
            is_error = bool(payload.get("is_error")) or payload.get("subtype") == "error"
            session_id = payload.get("session_id")
            self._on_message(
                ParsedMessage(
                    type=MessageType.RESULT,
                    content=result_text,
                    data={
                        "success": not is_error,
                        "error": result_text if is_error else None,
                        "result": result_text,
                        "session_id": session_id,
                        "raw": payload,
                    },
                )
            )
            if session_id:
                self._on_message(
                    ParsedMessage(type=MessageType.SESSION_ID, content=session_id, data=payload)
                )
            return

        if payload.get("error"):
            self._on_message(
                ParsedMessage(
                    type=MessageType.ERROR,
                    content=str(payload.get("error")),
                    data=payload,
                )
            )
