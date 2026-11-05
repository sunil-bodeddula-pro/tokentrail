"""Generate a month of made-up agent sessions and git history, so you can try TokenTrail without an agent.

    python3 examples/demo_data.py                  # writes ./tokentrail-demo
    tokentrail --config tokentrail-demo/config.json

Everything is fictional: three agents (a coding agent and two custom bots written in the generic event format), four
small git repositories, and runs of every health outcome. The config points TokenTrail at this folder only, so your
real agent history and store are never touched. The same --seed always produces the same data.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

REPOS = {
    "checkout-service": [
        "Add idempotency keys to the payment intent endpoint",
        "Fix the flaky refund integration test",
        "Retry webhook delivery with exponential backoff",
        "Why does the cart total round down for JPY?",
        "Add structured logging to the order pipeline",
    ],
    "web-dashboard": [
        "Make the revenue chart responsive on phones",
        "Add a dark mode toggle that remembers the choice",
        "The date picker shows the wrong week start in Germany",
        "Split the settings page into tabs",
        "Lazy-load the analytics bundle",
    ],
    "billing-api": [
        "Migrate invoices to the new tax rates table",
        "Add a dry-run flag to the proration job",
        "Investigate why monthly invoices are generated twice",
        "Write a migration to backfill customer currencies",
    ],
    "docs-site": [
        "Document the new webhooks retry policy",
        "Fix broken links in the API reference",
        "Write release notes for v2.4",
    ],
}
AGENTS = {  # name: (share of sessions, models with weights, skills it uses)
    "Claude Code": (
        0.62,
        {"claude-opus-5-5": 5, "claude-sonnet-5-5": 4},
        ["run-tests", "code-review", "db-migrations"],
    ),
    "Release Bot": (0.22, {"claude-sonnet-5-5": 3, "claude-haiku-5-5": 2}, ["release-notes", "changelog"]),
    "Support Triage": (0.16, {"claude-haiku-5-5": 5, "claude-sonnet-5-5": 1}, ["ticket-routing"]),
}
OUTCOMES = {"fast": 52, "standard": 30, "loop": 7, "wander": 6, "errors": 5}
READS = ["Read", "Grep", "Glob"]
EDITS = ["Edit", "Write"]
FILES = [
    "src/api/payments.py",
    "src/models/order.py",
    "tests/test_refunds.py",
    "src/ui/Chart.tsx",
    "README.md",
    "src/jobs/proration.py",
    "migrations/0042_tax_rates.sql",
    "docs/webhooks.md",
    "src/lib/money.ts",
]
COMMIT_TYPES = ["feat", "fix", "fix", "refactor", "test", "docs", "chore", "perf"]


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Session:
    def __init__(self, rnd: random.Random, out: str, agent: str, sid: str, workspace: str, start: datetime):
        self.rnd, self.agent, self.sid, self.workspace, self.t = rnd, agent, sid, workspace, start
        self.path = os.path.join(out, "events", agent.lower().replace(" ", "-"), f"{sid}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.rows: list[dict[str, Any]] = []
        self.context = rnd.randint(9_000, 16_000)  # cached prompt prefix grows over the conversation
        self.msg = 0

    def emit(self, event: str, **fields: Any) -> None:
        self.rows.append(
            {
                "event": event,
                "session_id": self.sid,
                "agent": self.agent,
                "ts": iso(self.t),
                "workspace": self.workspace,
                **fields,
            }
        )

    def tick(self, lo: float, hi: float) -> None:
        self.t += timedelta(seconds=self.rnd.uniform(lo, hi))

    def step(
        self, model: str, tool: str, target: str, error: bool = False, skill: str = "", subagent: bool = False
    ) -> None:
        r = self.rnd
        self.msg += 1
        output = r.randint(120, 900)
        usage = {
            "input": r.randint(30, 420),
            "output": output,
            "cache_read": self.context,
            "thinking": int(output * r.uniform(0.1, 0.5)),
        }
        if r.random() < 0.25:
            usage["cache_write"] = r.randint(800, 6_000)
        self.context += r.randint(300, 2_400)
        self.tick(2, 9)
        self.emit("response", model=model, message_id=f"{self.sid}-{self.msg}", usage=usage, subagent=subagent)
        self.emit("tool_call", tool=tool, target=target, skill=skill, subagent=subagent)
        self.tick(0.5, 6)
        self.emit("tool_result", chars=r.randint(150, 7_000), error=error, subagent=subagent)

    def run(self, prompt: str, model: str, outcome: str, skills: list[str]) -> None:
        r = self.rnd
        self.tick(20, 240)
        self.emit("prompt", text=prompt, chars=len(prompt))
        steps = {
            "fast": r.randint(6, 26),
            "standard": r.randint(32, 58),
            "loop": r.randint(18, 40),
            "wander": r.randint(48, 75),
            "errors": r.randint(14, 34),
        }[outcome]
        skill_used = outcome != "wander" and r.random() < 0.45
        loop_at = r.randint(4, max(5, steps - 6)) if outcome == "loop" else -1
        errors_left = {"errors": r.randint(4, 7), "standard": r.randint(0, 1), "loop": 0}.get(outcome, 0)
        subagent_span = range(r.randint(3, 8), r.randint(10, 16)) if outcome == "standard" and r.random() < 0.4 else ()
        i = 0
        while i < steps:
            sub = i in subagent_span
            if i == 1 and skill_used:
                self.step(model, "Skill", "", skill=r.choice(skills))
            elif i == loop_at:
                for _ in range(r.randint(4, 6)):  # the same failing command, again and again
                    self.step(model, "Bash", "pytest tests/test_refunds.py -x")
                i += 3
            elif outcome == "wander":
                self.step(model, r.choice(READS), r.choice(FILES), subagent=sub)
            else:
                roll = r.random()
                fail = errors_left > 0 and r.random() < 0.35
                if fail:
                    errors_left -= 1
                if roll < 0.45:
                    self.step(model, r.choice(READS), r.choice(FILES), subagent=sub)
                elif roll < 0.70:
                    self.step(model, r.choice(EDITS), r.choice(FILES), error=fail, subagent=sub)
                elif roll < 0.92:
                    self.step(
                        model,
                        "Bash",
                        r.choice(["npm test", "pytest -q", "make lint", "git status"]),
                        error=fail,
                        subagent=sub,
                    )
                else:
                    self.step(model, "WebSearch", "best practice " + r.choice(["idempotency", "retries", "a11y"]))
            i += 1

    def save(self, title: str) -> None:
        self.rows.insert(1, {**self.rows[0], "event": "title", "text": title})
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row) + "\n" for row in self.rows)


def git(repo: str, *args: str, when: datetime | None = None) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Demo Developer",
        "GIT_AUTHOR_EMAIL": "dev@example.com",
        "GIT_COMMITTER_NAME": "Demo Developer",
        "GIT_COMMITTER_EMAIL": "dev@example.com",
    }
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when.isoformat()
    subprocess.run(["git", "-C", repo, *args], env=env, check=True, capture_output=True)


def make_repo(rnd: random.Random, path: str, name: str, days: int, now: datetime) -> None:
    os.makedirs(path, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "dev@example.com")
    issue = rnd.randint(100, 400)
    for d in range(days, -1, -1):
        day = now - timedelta(days=d)
        if day.weekday() >= 5 and rnd.random() < 0.8:
            continue
        for _ in range(rnd.randint(0, 3)):
            when = day.replace(hour=rnd.randint(9, 18), minute=rnd.randint(0, 59))
            kind = rnd.choice(COMMIT_TYPES)
            issue += rnd.randint(1, 4)
            subject = f"{kind}({name.split('-', maxsplit=1)[0]}): {rnd.choice(REPOS[name]).lower()} (#{issue})"
            body = "\n\nCo-Authored-By: Claude <noreply@anthropic.com>" if rnd.random() < 0.6 else ""
            with open(os.path.join(path, "CHANGELOG.md"), "a", encoding="utf-8") as fh:
                fh.write(subject + "\n")
            git(path, "add", "-A")
            git(path, "commit", "-q", "-m", subject + body, when=when)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="tokentrail-demo", help="folder to create (default ./tokentrail-demo)")
    ap.add_argument("--days", type=int, default=30, help="days of history (default 30)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    out = os.path.abspath(args.out)
    if os.path.exists(os.path.join(out, "store")):
        raise SystemExit(f"{out} already has a store; pick another --out or delete the folder first")
    now = datetime.now(UTC).replace(microsecond=0)

    for name in REPOS:
        make_repo(rnd, os.path.join(out, "repos", name), name, args.days, now)

    n = 0
    for d in range(args.days, -1, -1):
        day = now - timedelta(days=d)
        for _ in range(rnd.randint(1, 3) if day.weekday() >= 5 else rnd.randint(3, 8)):
            agent = rnd.choices(list(AGENTS), [a[0] for a in AGENTS.values()])[0]
            _, models, skills = AGENTS[agent]
            repo = rnd.choice(list(REPOS))
            start = day.replace(hour=rnd.randint(8, 19), minute=rnd.randint(0, 59), second=0)
            if start > now:
                continue
            n += 1
            s = Session(rnd, out, agent, f"demo-{n:04d}", os.path.join(out, "repos", repo), start)
            model = rnd.choices(list(models), list(models.values()))[0]
            prompts = rnd.sample(REPOS[repo], k=min(len(REPOS[repo]), rnd.choice([1, 1, 2, 2, 3])))
            for p in prompts:
                s.run(p, model, rnd.choices(list(OUTCOMES), list(OUTCOMES.values()))[0], skills)
            s.save(prompts[0])

    config = {
        "store": os.path.join(out, "store"),
        "machine_id": "demo-laptop",
        "adapters": ["generic"],
        "events_dir": os.path.join(out, "events"),
        "author_emails": ["dev@example.com"],
        "git_days": args.days + 1,
    }
    with open(os.path.join(out, "config.json"), "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    print(f"Wrote {n} sessions and {len(REPOS)} git repositories to {out}")
    print(f"Open the dashboard:  tokentrail --config {os.path.join(out, 'config.json')}")


if __name__ == "__main__":
    main()
