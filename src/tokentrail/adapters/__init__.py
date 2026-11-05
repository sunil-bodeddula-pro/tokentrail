"""Adapters turn one agent's local logs into normalized Events.

An adapter is any object with:
    name: str                                   shown in the dashboard's Agent column
    def sources(self) -> list[str]              files to read (the collector caches them by size and mtime)
    def events(self, path: str) -> list[Event]  every Event in one file

To support a new agent, either write an adapter here and register it in ADAPTERS, or have the agent (or a wrapper
script) write the generic JSONL format that GenericJsonlAdapter reads; see docs/event-format.md.
"""

from .base import Adapter
from .claude_code import ClaudeCodeAdapter
from .generic_jsonl import GenericJsonlAdapter

ADAPTERS = {
    "claude-code": ClaudeCodeAdapter,
    "generic": GenericJsonlAdapter,
}

__all__ = ["ADAPTERS", "Adapter", "ClaudeCodeAdapter", "GenericJsonlAdapter"]
