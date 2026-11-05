"""What the dashboard serves: everything in the store, refreshed by a background sync loop."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .models import Health
from .segment import parse_ts
from .store import Store

if TYPE_CHECKING:
    from .mirror import Mirror
    from .sync import Syncer


class TelemetryState:
    def __init__(self, store: Store, syncer: Syncer | None = None, mirror: Mirror | None = None, days: int = 0):
        self.store = store
        self.syncer = syncer
        self.mirror = mirror
        self.days = days
        self._stop = threading.Event()
        self.last_pull: dict[str, Any] = {}

    def sync(self) -> dict[str, Any]:
        return self.syncer.run() if self.syncer else {}

    def pull(self) -> int:
        if not self.mirror:
            return 0
        n = self.mirror.pull()
        self.last_pull = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "files": n}
        return n

    def snapshot(self) -> dict[str, Any]:
        runs, commits, machines = self.store.read_all()
        if self.days:
            cutoff = datetime.now(UTC) - timedelta(days=self.days)
            runs = [r for r in runs if (t := parse_ts(r.get("started", ""))) and t >= cutoff]
            commits = [c for c in commits if (t := parse_ts(c.get("date", ""))) and t >= cutoff]
        runs.sort(key=lambda r: r.get("started", ""), reverse=True)
        return {
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "store": {
                "path": self.store.root,
                "machine": self.store.machine,
                "machines": machines,
                "remote": self.mirror.uri if self.mirror else "",
                "last_sync": self.syncer.last if self.syncer else {},
                "last_pull": self.last_pull,
            },
            "health_order": [h.value for h in Health],
            "runs": runs,
            "commits": commits,
        }

    def start(self, interval: int, pull_every: int = 300) -> None:
        """Sync every `interval` seconds; pull other machines' data every `pull_every` seconds when mirrored."""
        if interval <= 0 and not self.mirror:
            return

        def loop() -> None:
            last_pull = time.monotonic()
            while not self._stop.wait(max(interval, 5)):
                try:
                    if interval > 0:
                        self.sync()
                    if self.mirror and time.monotonic() - last_pull >= pull_every:
                        self.pull()
                        last_pull = time.monotonic()
                except Exception as exc:  # one failed sync (a network blip) must not stop the loop
                    print(f"sync failed: {exc}", flush=True)

        threading.Thread(target=loop, daemon=True, name="tokentrail-sync").start()

    def stop(self) -> None:
        self._stop.set()
