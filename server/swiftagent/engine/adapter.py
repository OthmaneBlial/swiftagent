"""Compatibility import for the pre-v0.3 Claude adapter path."""

from swiftagent.agents.claude.adapter import ClaudeCodeAdapter

ClaudeAdapter = ClaudeCodeAdapter

__all__ = ["ClaudeAdapter", "ClaudeCodeAdapter"]
