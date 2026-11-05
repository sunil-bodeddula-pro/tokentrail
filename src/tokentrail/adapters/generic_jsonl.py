"""The generic event format: any agent, wrapper or script can write it, and the dashboard reads it with no code changes.

One JSON object per line, in *.jsonl files under ~/.tokentrail/events/ (or a directory you pass with
--events-dir). Field reference: docs/event-format.md.
"""
from __future__ import annotations

import json

from ..models import Event, Kind
from .base import find_files

KINDS = {k.value: k for k in Kind}


class GenericJsonlAdapter:
    name = "Generic"

    def __init__(self, root: str = "~/.tokentrail/events"):
        self.root = root

    def sources(self) -> list[str]:
        return find_files(self.root, "**/*.jsonl")

    def events(self, path: str) -> list[Event]:
        out: list[Event] = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                kind = KINDS.get(d.get("event", ""))
                if not kind or not d.get("session_id"):
                    continue
                u = d.get("usage") or {}
                out.append(Event(
                    kind, ts=d.get("ts", ""), conversation_id=str(d["session_id"]), agent=d.get("agent") or self.name,
                    cwd=d.get("workspace", ""), model=d.get("model", ""), message_id=str(d.get("message_id", "")),
                    input_tokens=int(u.get("input", 0) or 0), output_tokens=int(u.get("output", 0) or 0),
                    cache_read_tokens=int(u.get("cache_read", 0) or 0), cache_write_tokens=int(u.get("cache_write", 0) or 0),
                    thinking_tokens=int(u.get("thinking", 0) or 0), tool=d.get("tool", ""), tool_id=str(d.get("tool_id", "")),
                    target=str(d.get("target", ""))[:300], is_error=bool(d.get("error")), chars=int(d.get("chars", 0) or 0),
                    text=str(d.get("text", ""))[:400], skill=d.get("skill", ""), subagent=bool(d.get("subagent"))))
        return out
