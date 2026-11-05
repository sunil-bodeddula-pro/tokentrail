"""Agent-neutral data model.

Every adapter turns its agent's logs into a stream of Events; segment.build_runs turns Events into TaskRun records;
analytics works only on TaskRun records. Adding an agent means writing an adapter, nothing else.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Kind(str, Enum):
    PROMPT = "prompt"            # a person asked for something: starts a new task run
    RESPONSE = "response"        # one model response (one step); carries token usage
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TITLE = "title"              # a conversation title, if the agent records one


@dataclass
class Event:
    kind: Kind
    ts: str                      # ISO 8601, UTC
    conversation_id: str
    agent: str = ""
    cwd: str = ""
    model: str = ""
    message_id: str = ""         # de-duplicates responses an agent logs in several pieces
    input_tokens: int = 0        # uncached input
    output_tokens: int = 0       # includes reasoning tokens
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0     # reasoning tokens, when the agent reports them separately
    tool: str = ""
    tool_id: str = ""
    target: str = ""             # file path, command or query the tool acted on
    is_error: bool = False
    chars: int = 0               # characters of prompt text or tool output
    text: str = ""               # prompt text (previewed) or title
    skill: str = ""              # skill name, when the call activated a skill
    subagent: bool = False       # the event happened inside a subagent


class Health(str, Enum):
    HIGH_VELOCITY = "High-Velocity (<=30 steps)"
    POSITIVE = "Positive (Standard)"
    TOOL_LOOPS = "Friction: Tool Loops"
    WANDERING = "Wandering: Zero File Writes"
    HIGH_ERRORS = "Failure: High Error Rate"


HEALTHY = {Health.HIGH_VELOCITY.value, Health.POSITIVE.value}


@dataclass
class TaskRun:
    run_id: str
    conversation_id: str
    agent: str
    title: str = ""
    prompt: str = ""
    model: str = ""
    models: list[str] = field(default_factory=list)
    workspace: str = ""
    cwd: str = ""
    started: str = ""
    ended: str = ""
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0
    prompt_chars: int = 0
    tool_output_chars: int = 0
    tools: dict[str, int] = field(default_factory=dict)
    tool_calls: int = 0
    tool_errors: int = 0
    file_writes: int = 0
    skills: list[str] = field(default_factory=list)
    subagent_steps: int = 0
    max_repeat: int = 0          # longest run of identical consecutive tool calls
    health: str = ""
    cost_usd: float = 0.0
    cache_savings_usd: float = 0.0
    priced: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Commit:
    sha: str
    repo: str
    author: str
    email: str
    date: str
    subject: str
    type: str = ""               # conventional commit type
    scope: str = ""
    issues: list[str] = field(default_factory=list)
    ai_tagged: bool = False
    mine: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
