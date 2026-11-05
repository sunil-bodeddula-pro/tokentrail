"""Command line entry point.

    python3 -m agent_observability.cli                      # dashboard on http://127.0.0.1:8765
    python3 -m agent_observability.cli --summary --days 30  # print a summary and exit
    python3 -m agent_observability.cli --export-json out.json --days 180
    python3 -m agent_observability.cli --export-csv runs.csv --days 180
"""
from __future__ import annotations

import argparse
import csv
import json
import sys

from .adapters import ADAPTERS, ClaudeCodeAdapter, GenericJsonlAdapter
from .analytics import breakdowns, kpis, roi, summary_text
from .collector import TelemetryCollector
from .models import Commit, TaskRun
from .pricing import Pricing
from .server import serve
from .state import TelemetryState

CSV_FIELDS = ["run_id", "conversation_id", "agent", "model", "workspace", "started", "ended", "steps", "input_tokens",
              "output_tokens", "cache_read_tokens", "cache_write_tokens", "thinking_tokens", "tool_calls", "tool_errors",
              "file_writes", "skills", "subagent_steps", "max_repeat", "health", "cost_usd", "priced", "title", "prompt"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent_observability", description="Local telemetry for AI coding agents.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sync-interval", type=int, default=30, help="seconds between background re-scans (0 = off)")
    p.add_argument("--days", type=int, default=180, help="how far back to read (default 180)")
    p.add_argument("--summary", action="store_true", help="print a summary and exit")
    p.add_argument("--export-json", metavar="FILE")
    p.add_argument("--export-csv", metavar="FILE")
    p.add_argument("--adapters", default=",".join(ADAPTERS), help=f"comma-separated: {', '.join(ADAPTERS)}")
    p.add_argument("--claude-dir", default="~/.claude/projects")
    p.add_argument("--events-dir", default="~/.agent-observability/events", help="generic JSONL events from any agent")
    p.add_argument("--pricing", metavar="FILE", help="JSON overrides: {model_prefix: [input, output, cache_read, cache_write]}")
    p.add_argument("--repo", action="append", default=[], help="extra git repository to include (repeatable)")
    p.add_argument("--author-email", action="append", default=[], help="treat commits by this email as yours (repeatable)")
    p.add_argument("--ai-tag", help="regex marking AI-assisted commits, in addition to Co-Authored-By trailers")
    p.add_argument("--no-git", action="store_true", help="skip git history")
    p.add_argument("--no-cache", action="store_true", help="don't read or write the on-disk parse cache")
    return p


def make_adapters(args) -> list:
    out = []
    for name in [a.strip() for a in args.adapters.split(",") if a.strip()]:
        if name == "claude-code":
            out.append(ClaudeCodeAdapter(args.claude_dir))
        elif name == "generic":
            out.append(GenericJsonlAdapter(args.events_dir))
        else:
            sys.exit(f"unknown adapter: {name} (choose from {', '.join(ADAPTERS)})")
    return out


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    collector = TelemetryCollector(make_adapters(args), Pricing(args.pricing), None if args.no_cache else "~/.cache/agent-observability/runs.json")
    state = TelemetryState(collector, args.days, args.repo, args.author_email, args.ai_tag, git=not args.no_git)

    if args.summary or args.export_json or args.export_csv:
        snap = state.sync()
        runs = [TaskRun(**d) for d in snap["runs"]]
        commits = [Commit(**d) for d in snap["commits"]]
        if args.summary:
            print(summary_text(runs, commits, args.days))
        if args.export_json:
            with open(args.export_json, "w", encoding="utf-8") as fh:
                json.dump({**snap, "kpis": kpis(runs), "breakdowns": breakdowns(runs), "roi": roi(runs, commits)}, fh, indent=1)
            print(f"wrote {args.export_json}")
        if args.export_csv:
            with open(args.export_csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
                w.writeheader()
                for r in runs:
                    d = r.to_dict()
                    d["skills"] = ";".join(d["skills"])
                    w.writerow(d)
            print(f"wrote {args.export_csv}")
        return 0

    print("Reading agent sessions…", flush=True)
    state.sync()
    print(f"  {collector.last_stats}", flush=True)
    state.start(args.sync_interval)
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
