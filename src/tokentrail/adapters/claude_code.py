"""Claude Code: one JSONL transcript per conversation under ~/.claude/projects/<project>/<session>.jsonl.

Assistant responses are logged one content block per line, every line repeating the same message id and usage, so
usage is taken once per message id (segment.build_runs de-duplicates). Tool results come back in user lines with an
is_error flag. Lines marked isSidechain belong to subagents.
"""

from __future__ import annotations

import json
import os

from ..models import Event, Kind
from .base import find_files, target_of

SKIP_PROMPT_PREFIXES = ("<local-command", "[Request interrupted", "Caveat:", "<system-reminder>")


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _result_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


class ClaudeCodeAdapter:
    name = "Claude Code"

    def __init__(self, root: str = "~/.claude/projects"):
        self.root = root

    def sources(self) -> list[str]:
        return find_files(self.root, "**/*.jsonl")

    def events(self, path: str) -> list[Event]:
        out: list[Event] = []
        fallback_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                kind = d.get("type")
                conv = d.get("sessionId") or fallback_id
                ts = d.get("timestamp", "")
                cwd = d.get("cwd", "")
                side = bool(d.get("isSidechain"))
                base = dict(ts=ts, conversation_id=conv, agent=self.name, cwd=cwd, subagent=side)
                if kind == "ai-title" and d.get("aiTitle"):
                    out.append(Event(Kind.TITLE, text=d["aiTitle"], **base))
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if kind == "assistant":
                    model = msg.get("model", "")
                    if model == "<synthetic>":
                        continue
                    u = msg.get("usage") or {}
                    out.append(
                        Event(
                            Kind.RESPONSE,
                            model=model,
                            message_id=msg.get("id", "") or d.get("uuid", ""),
                            input_tokens=u.get("input_tokens", 0) or 0,
                            output_tokens=u.get("output_tokens", 0) or 0,
                            cache_read_tokens=u.get("cache_read_input_tokens", 0) or 0,
                            cache_write_tokens=u.get("cache_creation_input_tokens", 0) or 0,
                            thinking_tokens=(u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0,
                            **base,
                        )
                    )
                    for b in content if isinstance(content, list) else []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            inp = b.get("input") or {}
                            name = b.get("name", "")
                            skill = inp.get("skill", "") if name == "Skill" else ""
                            if not skill and name == "Read":
                                fp = str(inp.get("file_path", ""))
                                if fp.endswith("/SKILL.md"):
                                    skill = fp.rstrip("/").split("/")[-2]
                            out.append(
                                Event(
                                    Kind.TOOL_CALL,
                                    tool=name,
                                    tool_id=b.get("id", ""),
                                    target=target_of(inp),
                                    skill=skill,
                                    model=model,
                                    **base,
                                )
                            )
                elif kind == "user":
                    if isinstance(content, list) and any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
                    ):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                out.append(
                                    Event(
                                        Kind.TOOL_RESULT,
                                        tool_id=b.get("tool_use_id", ""),
                                        is_error=bool(b.get("is_error")),
                                        chars=_result_chars(b.get("content")),
                                        **base,
                                    )
                                )
                        continue
                    if d.get("isMeta") or d.get("isCompactSummary") or side:
                        continue
                    text = _text_of(content).strip()
                    if not text or text.startswith(SKIP_PROMPT_PREFIXES):
                        continue
                    out.append(Event(Kind.PROMPT, text=text[:400], chars=len(text), **base))
        return out
