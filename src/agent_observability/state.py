"""The latest telemetry snapshot, refreshed by a background thread."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from .analytics import within
from .collector import TelemetryCollector
from .git_collector import collect_commits
from .models import Health


class TelemetryState:
    def __init__(self, collector: TelemetryCollector, days: int = 180, repos: list[str] | None = None,
                 author_emails: list[str] | None = None, ai_tag: str | None = None, git: bool = True):
        self.collector = collector
        self.days = days
        self.repos = repos or []
        self.author_emails = author_emails or []
        self.ai_tag = ai_tag
        self.git = git
        self._lock = threading.Lock()
        self._snapshot: dict = {}
        self._stop = threading.Event()

    def sync(self) -> dict:
        runs = within(self.collector.collect(), self.days)
        commits = []
        if self.git:
            paths = self.repos + sorted({r.cwd for r in runs if r.cwd})
            commits = collect_commits(paths, self.days, self.author_emails, self.ai_tag)
        snap = {
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window_days": self.days,
            "stats": self.collector.last_stats,
            "health_order": [h.value for h in Health],
            "runs": [r.to_dict() for r in sorted(runs, key=lambda r: r.started, reverse=True)],
            "commits": [c.to_dict() for c in commits],
        }
        with self._lock:
            self._snapshot = snap
        return snap

    def snapshot(self) -> dict:
        with self._lock:
            snap = self._snapshot
        return snap or self.sync()

    def start(self, interval: int):
        if interval <= 0:
            return

        def loop():
            while not self._stop.wait(interval):
                try:
                    self.sync()
                except Exception as exc:  # keep the dashboard alive if one sync fails
                    print(f"sync failed: {exc}", flush=True)

        threading.Thread(target=loop, daemon=True, name="telemetry-sync").start()

    def stop(self):
        self._stop.set()
