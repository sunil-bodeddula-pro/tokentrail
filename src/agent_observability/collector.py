"""Reads every adapter's files into TaskRun records, re-parsing only files that changed.

Each file is cached by (size, mtime_ns). A sync stats every file and re-parses only the changed ones, so a sync with
nothing new takes milliseconds even over hundreds of megabytes of transcripts. The cache is also written to disk
(~/.cache/agent-observability/runs.json) so a restart doesn't re-parse everything.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from .models import TaskRun
from .pricing import Pricing
from .segment import build_runs

CACHE_VERSION = 3


class TelemetryCollector:
    def __init__(self, adapters: list, pricing: Pricing, cache_file: str | None = "~/.cache/agent-observability/runs.json"):
        self.adapters = adapters
        self.pricing = pricing
        self.cache_file = os.path.expanduser(cache_file) if cache_file else None
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}      # path -> {"key": [size, mtime_ns], "runs": [dict, ...]}
        self._price_sig = hashlib.sha1(json.dumps(pricing.prices, sort_keys=True).encode()).hexdigest()[:12]
        self.last_stats: dict = {}
        self._load()

    def _load(self):
        if not self.cache_file or not os.path.exists(self.cache_file):
            return
        try:
            with open(self.cache_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("version") == CACHE_VERSION and data.get("pricing") == self._price_sig:
                self._cache = data.get("files", {})
        except (OSError, ValueError):
            self._cache = {}

    def _save(self):
        if not self.cache_file:
            return
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        tmp = self.cache_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": CACHE_VERSION, "pricing": self._price_sig, "files": self._cache}, fh)
        os.replace(tmp, self.cache_file)

    def collect(self) -> list[TaskRun]:
        """All runs from all adapters, re-parsing only changed files."""
        t0 = time.perf_counter()
        parsed = skipped = 0
        with self._lock:
            live = set()
            for adapter in self.adapters:
                for path in adapter.sources():
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    live.add(path)
                    key = [st.st_size, st.st_mtime_ns]
                    hit = self._cache.get(path)
                    if hit and hit["key"] == key:
                        skipped += 1
                        continue
                    runs = build_runs(adapter.events(path), self.pricing)
                    self._cache[path] = {"key": key, "runs": [r.to_dict() for r in runs]}
                    parsed += 1
            for gone in set(self._cache) - live:
                del self._cache[gone]
            if parsed:
                self._save()
            runs = [TaskRun(**d) for entry in self._cache.values() for d in entry["runs"]]
        self.last_stats = {"files": len(live), "parsed": parsed, "unchanged": skipped,
                           "runs": len(runs), "ms": round((time.perf_counter() - t0) * 1000, 1)}
        return runs
