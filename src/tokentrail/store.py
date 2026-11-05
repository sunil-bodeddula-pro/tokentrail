"""The telemetry store: TokenTrail's own copy of everything, kept even after agent history is deleted.

Layout (plain JSON files, one per conversation, so a sync rewrites only what changed):

    <store>/v1/<machine>/runs/<agent>/<conversation_id>.json   {"agent", "conversation_id", "source", "updated", "runs": [...]}
    <store>/v1/<machine>/commits/<repo>.json                    {"repo", "updated", "commits": [...]}
    <store>/v1/<machine>/manifest.json                          {"machine", "hostname", "version", "updated"}
    <store>/v1/<machine>/sources.json                           which agent files were read, by size and mtime (local only)

Rules: sync only adds and updates; nothing is deleted when an agent's history disappears. Writes go to a temporary
file and are renamed into place, so a crash never leaves a half-written file. Several machines can share one store
(through a bucket mirror); the reader merges them.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import uuid
from datetime import datetime, timezone

from . import __version__

FORMAT = "v1"
NOT_SENT_REMOTE = ("sources.json",)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "unknown"


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


class Store:
    def __init__(self, root: str, machine_id: str = ""):
        self.root = os.path.expanduser(root)
        os.makedirs(os.path.join(self.root, FORMAT), exist_ok=True)
        self.machine = slug(machine_id or self._local_machine_id())
        self.base = os.path.join(self.root, FORMAT, self.machine)
        self._read_cache: dict[str, tuple] = {}
        self._lock = threading.Lock()

    def _local_machine_id(self) -> str:
        """Kept in the store so the name stays the same across runs even without a config file."""
        path = os.path.join(self.root, ".machine-id")
        mid = read_json(path)
        if not mid:
            host = re.sub(r"[^a-z0-9-]+", "-", socket.gethostname().lower()).strip("-") or "machine"
            mid = f"{host[:24]}-{uuid.uuid4().hex[:4]}"
            write_json(path, mid)
        return mid

    # ---------- writing ----------
    def conversation_path(self, agent: str, conversation_id: str) -> str:
        return os.path.join(self.base, "runs", slug(agent), slug(conversation_id) + ".json")

    def upsert_conversation(self, agent: str, conversation_id: str, runs: list[dict], source: str = "") -> bool:
        """Save a conversation's runs. Returns True if the file changed.

        Normally the newly parsed runs replace the stored ones (the agent's file is the more complete record). If the
        agent's file has shrunk (history trimmed or compacted), stored runs that are no longer present are kept.
        """
        path = self.conversation_path(agent, conversation_id)
        old = read_json(path, {}) or {}
        stored = {r["run_id"]: r for r in old.get("runs", [])}
        fresh = {r["run_id"]: r for r in runs}
        if len(fresh) >= len(stored):
            merged = fresh
        else:
            merged = {**stored, **fresh}
        new_runs = sorted(merged.values(), key=lambda r: (r.get("started", ""), r["run_id"]))
        if new_runs == old.get("runs"):
            return False
        write_json(path, {"agent": agent, "conversation_id": conversation_id, "machine": self.machine,
                          "source": source, "updated": now_iso(), "runs": new_runs})
        return True

    def upsert_commits(self, repo: str, commits: list[dict]) -> bool:
        path = os.path.join(self.base, "commits", slug(repo) + ".json")
        old = read_json(path, {}) or {}
        merged = {c["sha"]: c for c in old.get("commits", [])}
        merged.update({c["sha"]: c for c in commits})
        new = sorted(merged.values(), key=lambda c: c.get("date", ""), reverse=True)
        if new == old.get("commits"):
            return False
        write_json(path, {"repo": repo, "machine": self.machine, "updated": now_iso(), "commits": new})
        return True

    def write_manifest(self) -> None:
        write_json(os.path.join(self.base, "manifest.json"),
                   {"machine": self.machine, "hostname": socket.gethostname(), "version": __version__, "updated": now_iso()})

    def sources(self) -> dict:
        return read_json(os.path.join(self.base, "sources.json"), {}) or {}

    def save_sources(self, data: dict) -> None:
        write_json(os.path.join(self.base, "sources.json"), data)

    # ---------- reading ----------
    def files(self) -> list[str]:
        """Every data file in the store, for all machines, relative to the store root."""
        out = []
        top = os.path.join(self.root, FORMAT)
        for dirpath, _, names in os.walk(top):
            for n in names:
                if n.endswith(".json") and not n.endswith(".tmp"):
                    out.append(os.path.relpath(os.path.join(dirpath, n), self.root).replace(os.sep, "/"))
        return sorted(out)

    def _load(self, rel: str):
        path = os.path.join(self.root, rel)
        try:
            st = os.stat(path)
        except OSError:
            return None
        key = (st.st_size, st.st_mtime_ns)
        hit = self._read_cache.get(rel)
        if hit and hit[0] == key:
            return hit[1]
        data = read_json(path)
        self._read_cache[rel] = (key, data)
        return data

    def read_all(self) -> tuple[list[dict], list[dict], list[str]]:
        """(runs, commits, machines) across every machine in the store. Unchanged files come from memory."""
        runs, commits, machines = [], [], set()
        with self._lock:
            for rel in self.files():
                parts = rel.split("/")
                if len(parts) < 4:
                    continue
                machine, kind = parts[1], parts[2]
                data = self._load(rel)
                if not isinstance(data, dict):
                    continue
                if kind == "runs":
                    machines.add(machine)
                    for r in data.get("runs", []):
                        runs.append({**r, "machine": machine})
                elif kind == "commits":
                    for c in data.get("commits", []):
                        commits.append({**c, "machine": machine})
        seen, unique = set(), []
        for c in sorted(commits, key=lambda c: c.get("date", ""), reverse=True):
            if c["sha"] not in seen:          # the same repository can be synced from two machines
                seen.add(c["sha"])
                unique.append(c)
        return runs, unique, sorted(machines)
