"""Events -> TaskRun records, and the health classification.

A task run starts at each prompt from a person and lasts until the next one, so it measures what one request cost.
Thresholds follow the dashboard guide in README.md section 3.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime
from functools import lru_cache

from .models import Event, Health, Kind, TaskRun
from .pricing import Pricing

WRITE_TOOLS = re.compile(r"(^|_)(write|edit|multiedit|replace|create_file|apply_patch|str_replace|notebookedit)", re.I)
NO_RESPONSE = "no response"
HIGH_VELOCITY_STEPS = 30
LOOP_REPEATS = 4
WANDER_STEPS = 45
ERROR_COUNT = 4
ERROR_RATE = 0.20
ERROR_RATE_MIN_STEPS = 6


@lru_cache(maxsize=4096)
def workspace_of(cwd: str) -> str:
    """The repository (or folder) name, walking up to the nearest .git when it exists on this machine."""
    if not cwd:
        return ""
    path = cwd
    while path and path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, ".git")):
            return os.path.basename(path)
        path = os.path.dirname(path)
    return os.path.basename(cwd.rstrip("/"))


def parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def classify(run: TaskRun) -> str:
    steps = max(run.steps, 1)
    rate = run.tool_errors / max(run.tool_calls, steps)
    if run.tool_errors >= ERROR_COUNT or (run.steps >= ERROR_RATE_MIN_STEPS and rate >= ERROR_RATE):
        return Health.HIGH_ERRORS.value
    if run.max_repeat >= LOOP_REPEATS:
        return Health.TOOL_LOOPS.value
    if run.steps > WANDER_STEPS and run.file_writes == 0 and not run.skills:
        return Health.WANDERING.value
    if run.steps <= HIGH_VELOCITY_STEPS and run.tool_errors == 0:
        return Health.HIGH_VELOCITY.value
    return Health.POSITIVE.value


def build_runs(events: list[Event], pricing: Pricing) -> list[TaskRun]:
    """Group events by conversation, split each at prompts, and total each run."""
    by_conv: dict[str, list[Event]] = {}
    for e in events:
        by_conv.setdefault(e.conversation_id, []).append(e)
    runs: list[TaskRun] = []
    for conv, evs in by_conv.items():
        evs.sort(key=lambda e: e.ts or "")
        title = next((e.text for e in reversed(evs) if e.kind == Kind.TITLE), "")
        seen_msgs: set[str] = set()
        current: TaskRun | None = None
        n = 0
        last_call, repeat = None, 0
        model_counts: Counter[str] = Counter()

        def finish(r: TaskRun | None, model_counts: Counter[str]) -> None:
            if r is None or (r.steps == 0 and not r.prompt):
                return
            r.models = [m for m, _ in model_counts.most_common()]
            r.model = r.models[0] if r.models else NO_RESPONSE
            r.health = classify(r)
            runs.append(r)

        for e in evs:
            if e.kind == Kind.TITLE:
                continue
            if e.kind == Kind.PROMPT or current is None:
                if e.kind == Kind.PROMPT:
                    finish(current, model_counts)
                    current = None
                n += 1
                current = TaskRun(
                    run_id=f"{conv}#{n}",
                    conversation_id=conv,
                    agent=e.agent,
                    title=title,
                    cwd=e.cwd,
                    workspace=workspace_of(e.cwd),
                    started=e.ts,
                    ended=e.ts,
                )
                model_counts = Counter()
                last_call, repeat = None, 0
                if e.kind == Kind.PROMPT:
                    current.prompt, current.prompt_chars = e.text, e.chars
                    continue
            r = current
            if e.ts:
                r.ended = max(r.ended, e.ts) if r.ended else e.ts
            if e.kind == Kind.RESPONSE:
                key = e.message_id or f"{e.ts}:{e.output_tokens}"
                if key in seen_msgs:
                    continue
                seen_msgs.add(key)
                r.steps += 1
                if e.subagent:
                    r.subagent_steps += 1
                r.input_tokens += e.input_tokens
                r.output_tokens += e.output_tokens
                r.cache_read_tokens += e.cache_read_tokens
                r.cache_write_tokens += e.cache_write_tokens
                r.thinking_tokens += e.thinking_tokens
                if e.model:
                    model_counts[e.model] += 1
                    c = pricing.cost(
                        e.model, e.input_tokens, e.output_tokens, e.cache_read_tokens, e.cache_write_tokens
                    )
                    if c is None:
                        r.priced = False
                    else:
                        r.cost_usd += c
                        r.cache_savings_usd += pricing.cache_savings(e.model, e.cache_read_tokens)
            elif e.kind == Kind.TOOL_CALL:
                r.tool_calls += 1
                r.tools[e.tool] = r.tools.get(e.tool, 0) + 1
                if WRITE_TOOLS.search(e.tool):
                    r.file_writes += 1
                if e.skill and e.skill not in r.skills:
                    r.skills.append(e.skill)
                call = (e.tool, e.target)
                repeat = repeat + 1 if call == last_call and e.target else 1
                last_call = call
                r.max_repeat = max(r.max_repeat, repeat)
            elif e.kind == Kind.TOOL_RESULT:
                r.tool_output_chars += e.chars
                if e.is_error:
                    r.tool_errors += 1
        finish(current, model_counts)
    for r in runs:
        r.cost_usd = round(r.cost_usd, 6)
        r.cache_savings_usd = round(r.cache_savings_usd, 6)
    return runs
