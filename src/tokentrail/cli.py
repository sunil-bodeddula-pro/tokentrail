"""TokenTrail command line.

    tokentrail init                 choose where to keep your data (a folder, or a gs:// / s3:// bucket) and save it
    tokentrail dashboard            sync in the background and open the dashboard (the default command)
    tokentrail daemon               sync every 30 s with no dashboard; `tokentrail service install` runs it at login
    tokentrail sync                 sync once and exit
    tokentrail pull                 download other machines' data from the remote (and restore anything missing)
    tokentrail status               where data lives, how much there is, when it last synced
    tokentrail summary --days 30    print the headline numbers
    tokentrail export --json F --csv F
    tokentrail service install|uninstall|print
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

from . import __version__, config as cfgmod, service
from .adapters import ADAPTERS, ClaudeCodeAdapter, GenericJsonlAdapter
from .analytics import breakdowns, kpis, roi, summary_text
from .mirror import Mirror
from .models import Commit, TaskRun
from .pricing import Pricing
from .server import serve
from .state import TelemetryState
from .store import Store
from .sync import Syncer

CSV_FIELDS = ["run_id", "conversation_id", "agent", "machine", "model", "workspace", "started", "ended", "steps",
              "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "thinking_tokens", "tool_calls",
              "tool_errors", "file_writes", "skills", "subagent_steps", "max_repeat", "health", "cost_usd", "priced",
              "title", "prompt"]


def add_common(p: argparse.ArgumentParser):
    p.add_argument("--config", help="config file (default ~/.config/tokentrail/config.json)")
    p.add_argument("--store", help="local store folder (overrides the config)")
    p.add_argument("--remote", help="remote mirror: gs://bucket/path, s3://bucket/path, file:///path (overrides the config)")
    p.add_argument("--no-remote", action="store_true", help="ignore the configured remote for this command")
    p.add_argument("--days", type=int, default=0, help="only show the last N days (default: everything)")
    p.add_argument("--no-git", action="store_true", help="don't read git history")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tokentrail", description="Local telemetry for AI coding agents.")
    p.add_argument("--version", action="version", version=f"tokentrail {__version__}")
    sub = p.add_subparsers(dest="cmd")

    i = sub.add_parser("init", help="choose where data is kept and save the settings")
    add_common(i)
    i.add_argument("--interval", type=int, help="seconds between syncs (default 30)")
    i.add_argument("--keep-prompts-remote", action="store_true", help="upload prompt text to the remote too (off by default)")
    i.add_argument("--service", action="store_true", help="also install the background sync service")
    i.add_argument("--yes", "-y", action="store_true", help="accept defaults without asking")

    d = sub.add_parser("dashboard", help="sync in the background and serve the dashboard")
    add_common(d)
    d.add_argument("--host", default="127.0.0.1")
    d.add_argument("--port", type=int, default=8765)
    d.add_argument("--interval", type=int, help="seconds between syncs; 0 = read the store only")

    for name, helptext in (("daemon", "sync on a timer with no dashboard"), ("sync", "sync once"),
                           ("pull", "download other machines' data"), ("status", "show where data lives and when it synced")):
        s = sub.add_parser(name, help=helptext)
        add_common(s)
        if name == "daemon":
            s.add_argument("--interval", type=int)

    s = sub.add_parser("summary", help="print the headline numbers")
    add_common(s)
    e = sub.add_parser("export", help="write JSON and/or CSV")
    add_common(e)
    e.add_argument("--json", metavar="FILE")
    e.add_argument("--csv", metavar="FILE")

    sv = sub.add_parser("service", help="run the sync daemon at login")
    sv.add_argument("action", choices=["install", "uninstall", "print"])
    return p


def settings(args) -> cfgmod.Config:
    cfg = cfgmod.load(getattr(args, "config", None))
    if getattr(args, "store", None):
        cfg.store = args.store
    if getattr(args, "remote", None):
        cfg.remote = args.remote
    if getattr(args, "no_remote", False):
        cfg.remote = ""
    if getattr(args, "interval", None) is not None:
        cfg.sync_interval = args.interval
    return cfg


def make_adapters(cfg: cfgmod.Config) -> list:
    out = []
    for name in cfg.adapters:
        if name == "claude-code":
            out.append(ClaudeCodeAdapter(cfg.claude_dir))
        elif name == "generic":
            out.append(GenericJsonlAdapter(cfg.events_dir))
        else:
            sys.exit(f"unknown adapter in config: {name} (choose from {', '.join(ADAPTERS)})")
    return out


def wire(cfg: cfgmod.Config, args) -> tuple[Store, Syncer, Mirror | None]:
    store = Store(cfg.store_path, cfg.machine_id)
    mirror = Mirror(store, cfg.remote, cfg.redact_remote) if cfg.remote else None
    syncer = Syncer(store, make_adapters(cfg), Pricing(cfg.pricing or None), cfg.repos, cfg.author_emails,
                    cfg.ai_tag or None, cfg.git_days, git=not getattr(args, "no_git", False), mirror=mirror)
    return store, syncer, mirror


def ask(prompt: str, default: str, yes: bool) -> str:
    if yes or not sys.stdin.isatty():
        return default
    got = input(f"{prompt} [{default}]: ").strip()
    return got or default


def cmd_init(args) -> int:
    cfg = settings(args)
    print("TokenTrail keeps its own copy of your agents' telemetry, so it survives when agent history is cleared.")
    cfg.store = ask("Local store folder", cfg.store, args.yes)
    cfg.remote = ask("Remote mirror (gs://bucket/path, s3://bucket/path, or blank for none)", cfg.remote, args.yes)
    cfg.sync_interval = int(ask("Seconds between syncs", str(cfg.sync_interval), args.yes))
    if args.keep_prompts_remote:
        cfg.redact_remote = False
    path = cfg.save(args.config)
    print(f"Saved {path}")
    store, syncer, mirror = wire(cfg, args)
    print(f"Machine name: {store.machine}")
    if mirror:
        print(f"Checking the remote {cfg.remote}…")
        mirror.backend.list("v1/")           # fails early, with a clear message, if credentials or the add-on are missing
        print("  remote reachable." + ("  Prompt text stays local (redacted before upload)." if cfg.redact_remote else ""))
    print("First sync…")
    print(f"  {syncer.run()}")
    if args.service:
        print(service.install())
    else:
        print("Next: `tokentrail dashboard` to view it, and `tokentrail service install` to keep syncing in the background.")
    return 0


def cmd_status(cfg, store: Store, mirror, config_file: str) -> int:
    files = store.files()
    size = sum(os.path.getsize(os.path.join(store.root, f)) for f in files)
    runs, commits, machines = store.read_all()
    manifest_path = os.path.join(store.base, "manifest.json")
    print(f"Config        {config_file}{'' if os.path.exists(config_file) else ' (not created yet: run tokentrail init)'}")
    print(f"Store         {store.root}  ({len(files)} files, {size / 1e6:.1f} MB)")
    print(f"This machine  {store.machine}")
    print(f"Machines      {', '.join(machines) or 'none yet'}")
    print(f"Remote        {cfg.remote or 'none'}{' (prompts redacted)' if cfg.remote and cfg.redact_remote else ''}")
    print(f"Data          {len(runs):,} task runs, {len({r['conversation_id'] for r in runs}):,} conversations, {len(commits):,} commits")
    if os.path.exists(manifest_path):
        print(f"Last sync     {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(manifest_path)))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"init", "dashboard", "daemon", "sync", "pull", "status", "summary", "export", "service"}
    if not argv or (argv[0] not in commands and argv[0] not in ("-h", "--help", "--version")):
        argv = ["dashboard", *argv]                  # `tokentrail` and `tokentrail --port 9000` open the dashboard
    args = build_parser().parse_args(argv)
    cmd = args.cmd
    if cmd == "service":
        print({"install": service.install, "uninstall": service.uninstall, "print": service.describe}[args.action]())
        return 0
    if cmd == "init":
        return cmd_init(args)

    cfg = settings(args)
    store, syncer, mirror = wire(cfg, args)
    state = TelemetryState(store, syncer, mirror, args.days)

    if cmd == "status":
        return cmd_status(cfg, store, mirror, args.config or cfgmod.config_path())
    if cmd == "sync":
        print(syncer.run())
        return 0
    if cmd == "pull":
        if not mirror:
            sys.exit("No remote configured: run `tokentrail init` or pass --remote.")
        print(f"Downloaded {state.pull()} files from {cfg.remote}")
        return 0
    if cmd == "daemon":
        print(f"TokenTrail syncing every {cfg.sync_interval}s into {store.root}" + (f", mirrored to {cfg.remote}" if mirror else ""), flush=True)
        print(f"  {syncer.run()}", flush=True)
        state.start(cfg.sync_interval)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    if cmd in ("summary", "export"):
        syncer.run()
        snap = state.snapshot()
        runs = [TaskRun(**{k: v for k, v in d.items() if k in TaskRun.__dataclass_fields__}) for d in snap["runs"]]
        commits = [Commit(**{k: v for k, v in d.items() if k in Commit.__dataclass_fields__}) for d in snap["commits"]]
        if cmd == "summary":
            print(summary_text(runs, commits, args.days))
            return 0
        if not (args.json or args.csv):
            sys.exit("export needs --json FILE and/or --csv FILE")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump({**snap, "kpis": kpis(runs), "breakdowns": breakdowns(runs), "roi": roi(runs, commits)}, fh, indent=1)
            print(f"wrote {args.json}")
        if args.csv:
            with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
                w.writeheader()
                for d in snap["runs"]:
                    w.writerow({**d, "skills": ";".join(d.get("skills", []))})
            print(f"wrote {args.csv}")
        return 0

    # dashboard
    print(f"Store: {store.root}" + (f"  (mirror: {cfg.remote})" if mirror else ""), flush=True)
    if mirror:
        print(f"  pulled {state.pull()} files from the remote", flush=True)
    if cfg.sync_interval > 0:
        print(f"  {syncer.run()}", flush=True)
    state.start(cfg.sync_interval)
    serve(state, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
