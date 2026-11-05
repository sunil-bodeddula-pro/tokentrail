"""Aggregates for the CLI summary and the JSON export. The dashboard computes the same figures in the browser so its
filters respond instantly; tests/test_analytics.py pins the definitions both follow (README section 3.3)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from .models import HEALTHY, Commit, Health, TaskRun
from .segment import parse_ts


def within(runs: list[TaskRun], days: int | None) -> list[TaskRun]:
    if not days:
        return runs
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [r for r in runs if (t := parse_ts(r.started)) and t >= cutoff]


def kpis(runs: list[TaskRun]) -> dict:
    n = len(runs)
    inp = sum(r.input_tokens + r.cache_write_tokens for r in runs)
    out = sum(r.output_tokens for r in runs)
    read = sum(r.cache_read_tokens for r in runs)
    steps = sum(r.steps for r in runs)
    calls = sum(r.tool_calls for r in runs)
    errors = sum(r.tool_errors for r in runs)
    healthy = sum(1 for r in runs if r.health in HEALTHY)
    fast = sum(1 for r in runs if r.health == Health.HIGH_VELOCITY.value)
    return {
        "sessions": n,
        "conversations": len({r.conversation_id for r in runs}),
        "tokens": inp + out,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": read,
        "cache_hit_pct": round(100 * read / (inp + read), 1) if inp + read else 0.0,
        "cost_usd": round(sum(r.cost_usd for r in runs), 2),
        "cache_savings_usd": round(sum(r.cache_savings_usd for r in runs), 2),
        "unpriced_runs": sum(1 for r in runs if not r.priced),
        "avg_steps": round(steps / n, 1) if n else 0.0,
        "healthy_pct": round(100 * healthy / n, 1) if n else 0.0,
        "high_velocity_pct": round(100 * fast / n, 1) if n else 0.0,
        "tool_calls": calls,
        "tool_error_pct": round(100 * errors / max(calls, steps), 2) if max(calls, steps) else 0.0,
    }


def breakdowns(runs: list[TaskRun]) -> dict:
    models, health, tools, skills, workspaces, agents = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    for r in runs:
        models[r.model or "no response"] += 1
        health[r.health] += 1
        workspaces[r.workspace or "unknown"] += 1
        agents[r.agent] += 1
        tools.update(r.tools)
        skills.update(r.skills)
    return {"models": models.most_common(), "health": health.most_common(), "tools": tools.most_common(15),
            "skills": skills.most_common(15), "workspaces": workspaces.most_common(), "agents": agents.most_common()}


def roi(runs: list[TaskRun], commits: list[Commit]) -> dict:
    mine = [c for c in commits if c.mine]
    k = kpis(runs)
    n = len(mine)
    return {
        "my_commits": n,
        "ai_tagged": sum(1 for c in mine if c.ai_tagged),
        "tokens_per_commit": round(k["tokens"] / n) if n else None,
        "steps_per_commit": round(sum(r.steps for r in runs) / n, 1) if n else None,
        "cost_per_commit": round(k["cost_usd"] / n, 2) if n else None,
        "issues_linked": len({i for c in mine for i in c.issues}),
    }


def summary_text(runs: list[TaskRun], commits: list[Commit], days: int | None) -> str:
    k, b = kpis(runs), breakdowns(runs)
    lines = [f"Agent telemetry, {'last ' + str(days) + ' days' if days else 'all time'}",
             f"  Sessions        {k['sessions']:,} task runs in {k['conversations']:,} conversations",
             f"  Tokens          {k['tokens'] / 1e6:,.2f}M (cache read {k['cache_read_tokens'] / 1e6:,.1f}M, hit {k['cache_hit_pct']}%)",
             f"  Est. cost       ${k['cost_usd']:,.2f}" + (f" ({k['unpriced_runs']} runs unpriced)" if k["unpriced_runs"] else ""),
             f"  Avg steps/run   {k['avg_steps']}",
             f"  Healthy         {k['healthy_pct']}%   high velocity {k['high_velocity_pct']}%",
             f"  Tool calls      {k['tool_calls']:,}   error rate {k['tool_error_pct']}%",
             "  Models          " + ", ".join(f"{m} ({c})" for m, c in b["models"][:5]),
             "  Health          " + ", ".join(f"{h} ({c})" for h, c in b["health"]),
             "  Top tools       " + ", ".join(f"{t} ({c})" for t, c in b["tools"][:8]),
             "  Skills          " + (", ".join(f"{s} ({c})" for s, c in b["skills"][:8]) or "none")]
    r = roi(runs, commits)
    if commits:
        lines.append(f"  Commits (mine)  {r['my_commits']} ({r['ai_tagged']} AI-credited), "
                     f"{r['tokens_per_commit'] or 0:,} tokens and ${r['cost_per_commit'] or 0} per commit")
    return "\n".join(lines)
