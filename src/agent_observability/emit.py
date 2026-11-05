"""Write generic events from your own agent or wrapper, so the dashboard picks it up with no adapter.

    from agent_observability.emit import EventLog
    log = EventLog(agent="My Agent", session_id="2026-11-04-a")
    log.prompt("Refactor the billing module")
    log.response(model="gpt-x", input=1200, output=300, cache_read=8000)
    log.tool_call("edit_file", target="billing.py")
    log.tool_result(error=False, chars=420)

Events append to ~/.agent-observability/events/<agent>/<session_id>.jsonl. Field reference: docs/event-format.md.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone


class EventLog:
    def __init__(self, agent: str, session_id: str | None = None, workspace: str | None = None,
                 root: str = "~/.agent-observability/events"):
        self.agent = agent
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.workspace = workspace or os.getcwd()
        folder = os.path.join(os.path.expanduser(root), re.sub(r"[^\w.-]+", "-", agent).strip("-") or "agent")
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, f"{self.session_id}.jsonl")

    def _write(self, event: str, **fields):
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "session_id": self.session_id, "agent": self.agent, "workspace": self.workspace, "event": event}
        row.update({k: v for k, v in fields.items() if v not in (None, "", {})})
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def title(self, text: str):
        self._write("title", text=text)

    def prompt(self, text: str):
        self._write("prompt", text=text[:400], chars=len(text))

    def response(self, model: str, input: int = 0, output: int = 0, cache_read: int = 0, cache_write: int = 0,
                 thinking: int = 0, message_id: str | None = None):
        usage = {k: v for k, v in dict(input=input, output=output, cache_read=cache_read, cache_write=cache_write,
                                         thinking=thinking).items() if v}
        self._write("response", model=model, usage=usage, message_id=message_id or uuid.uuid4().hex[:12])

    def tool_call(self, tool: str, target: str = "", skill: str = "", tool_id: str = ""):
        self._write("tool_call", tool=tool, target=target, skill=skill, tool_id=tool_id)

    def tool_result(self, error: bool = False, chars: int = 0, tool_id: str = ""):
        self._write("tool_result", error=error or None, chars=chars, tool_id=tool_id)
