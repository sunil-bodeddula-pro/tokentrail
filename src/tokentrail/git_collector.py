"""Local git history for the repositories your agents worked in.

Repositories are discovered from the working directories in the agent sessions (plus any you pass with --repo).
For each commit: conventional-commit type and scope, linked issues (#123, ABC-123, b/123), whether you wrote it
(your git user.email, or --author-email), and whether an AI agent is credited (a Co-Authored-By trailer naming a known
agent, or a tag matching --ai-tag).
"""
from __future__ import annotations

import os
import re
import subprocess

from .models import Commit

CONVENTIONAL = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?!?:\s")
ISSUES = re.compile(r"(?<![\w/])(#\d+|[A-Z][A-Z0-9]+-\d+|b/\d+)\b")
AI_TRAILER = re.compile(r"co-authored-by:.*\b(claude|copilot|gemini|cursor|codex|devin|aider|windsurf|jules|amazon q)\b", re.I)
SEP, END = "\x1f", "\x1e"


def git_root(path: str) -> str | None:
    if not path or not os.path.isdir(path):
        return None
    try:
        out = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def my_email(repo: str) -> str:
    try:
        out = subprocess.run(["git", "-C", repo, "config", "user.email"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_log(text: str, repo: str, me: set[str], ai_tag: re.Pattern | None) -> list[Commit]:
    commits = []
    for rec in text.split(END):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(SEP)
        if len(parts) < 6:
            continue
        sha, author, email, date, subject, body = parts[:6]
        m = CONVENTIONAL.match(subject)
        whole = subject + "\n" + body
        commits.append(Commit(
            sha=sha, repo=repo, author=author, email=email.lower(), date=date, subject=subject,
            type=m.group("type") if m else "", scope=(m.group("scope") or "") if m else "",
            issues=sorted(set(ISSUES.findall(whole))),
            ai_tagged=bool(AI_TRAILER.search(body) or (ai_tag and ai_tag.search(whole))),
            mine=email.lower() in me))
    return commits


def collect_commits(paths: list[str], days: int = 180, author_emails: list[str] | None = None,
                    ai_tag: str | None = None) -> list[Commit]:
    roots = sorted({r for r in (git_root(p) for p in paths) if r})
    tag = re.compile(ai_tag) if ai_tag else None
    out: list[Commit] = []
    for root in roots:
        me = {e.lower() for e in (author_emails or [])} | ({my_email(root)} - {""})
        fmt = SEP.join(["%H", "%an", "%ae", "%aI", "%s", "%b"]) + END
        try:
            res = subprocess.run(["git", "-C", root, "log", f"--since={days} days ago", f"--format={fmt}"],
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if res.returncode == 0:
            out.extend(parse_log(res.stdout, os.path.basename(root), me, tag))
    out.sort(key=lambda c: c.date, reverse=True)
    return out
