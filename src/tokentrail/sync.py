"""One sync: read changed agent files into the store, refresh git history, and push to the remote mirror if set.

Agent files are re-read only when their size or modification time changed, so a sync with nothing new takes
milliseconds. Nothing in the store is removed when an agent file disappears.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

from .git_collector import collect_commits
from .pricing import Pricing
from .segment import build_runs
from .store import Store


class Syncer:
    def __init__(self, store: Store, adapters: list, pricing: Pricing, repos: list[str] | None = None,
                 author_emails: list[str] | None = None, ai_tag: str | None = None, git_days: int = 365,
                 git: bool = True, mirror=None, git_every: int = 300):
        self.store = store
        self.adapters = adapters
        self.pricing = pricing
        self.repos = repos or []
        self.author_emails = author_emails or []
        self.ai_tag = ai_tag
        self.git_days = git_days
        self.git = git
        self.mirror = mirror
        self.git_every = git_every            # git history changes slowly; re-read it every few minutes, not every sync
        self._git_at = float("-inf")
        self._git_cwds: set[str] = set()
        self._manifest_at = float("-inf")
        self._lock = threading.Lock()
        self.last: dict = {}

    def run(self) -> dict:
        with self._lock:
            t0 = time.perf_counter()
            seen = self.store.sources()
            parsed = unchanged = changed_convs = 0
            cwds: set[str] = set()
            for adapter in self.adapters:
                for path in adapter.sources():
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    key = [st.st_size, st.st_mtime_ns, self.pricing.fingerprint]
                    entry = seen.get(path)
                    if entry and entry.get("key") == key:
                        unchanged += 1
                        cwds.update(entry.get("cwds", []))
                        continue
                    runs = build_runs(adapter.events(path), self.pricing)
                    by_conv = defaultdict(list)
                    for r in runs:
                        by_conv[r.conversation_id].append(r.to_dict())
                    for conv, rs in by_conv.items():
                        if self.store.upsert_conversation(adapter.name, conv, rs, source=path):
                            changed_convs += 1
                    file_cwds = sorted({r.cwd for r in runs if r.cwd})
                    cwds.update(file_cwds)
                    seen[path] = {"key": key, "agent": adapter.name, "cwds": file_cwds}
                    parsed += 1
            if parsed:
                self.store.save_sources(seen)
            commits_changed = 0
            git_due = time.monotonic() - self._git_at >= self.git_every or set(cwds) != self._git_cwds
            if self.git and git_due:
                self._git_at, self._git_cwds = time.monotonic(), set(cwds)
                by_repo = defaultdict(list)
                for c in collect_commits(sorted(cwds) + self.repos, self.git_days, self.author_emails, self.ai_tag):
                    by_repo[c.repo].append(c.to_dict())
                for repo, cs in by_repo.items():
                    commits_changed += self.store.upsert_commits(repo, cs)
            if parsed or commits_changed or time.monotonic() - self._manifest_at > 600:
                self.store.write_manifest()
                self._manifest_at = time.monotonic()
            pushed = self.mirror.push() if self.mirror else None
            self.last = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "files": parsed + unchanged, "parsed": parsed,
                         "unchanged": unchanged, "conversations_changed": changed_convs, "repos_changed": commits_changed,
                         "pushed": pushed, "ms": round((time.perf_counter() - t0) * 1000, 1)}
            return self.last
