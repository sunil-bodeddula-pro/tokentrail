"""Settings, saved by `tokentrail init` to ~/.config/tokentrail/config.json (%APPDATA%\\tokentrail on Windows).

Every setting can also be given on the command line, which wins over the file. TOKENTRAIL_CONFIG points at a
different file.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field


def config_dir() -> str:
    if platform.system() == "Windows" and os.environ.get("APPDATA"):
        return os.path.join(os.environ["APPDATA"], "tokentrail")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "tokentrail")


def config_path() -> str:
    return os.environ.get("TOKENTRAIL_CONFIG") or os.path.join(config_dir(), "config.json")


@dataclass
class Config:
    store: str = "~/.tokentrail/store"  # local folder: the system of record
    remote: str = ""  # optional mirror: gs://, s3:// or file://
    machine_id: str = ""  # blank: the store keeps a stable name in <store>/.machine-id
    sync_interval: int = 30
    redact_remote: bool = True  # strip prompt text and titles before uploading
    claude_dir: str = "~/.claude/projects"
    events_dir: str = "~/.tokentrail/events"
    adapters: list[str] = field(default_factory=lambda: ["claude-code", "generic"])
    pricing: str = ""
    repos: list[str] = field(default_factory=list)
    author_emails: list[str] = field(default_factory=list)
    ai_tag: str = ""
    git_days: int = 365

    @property
    def store_path(self) -> str:
        return os.path.expanduser(self.store)

    def save(self, path: str | None = None) -> str:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        return path


def load(path: str | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        known = Config.__dataclass_fields__
        cfg = Config(**{k: v for k, v in data.items() if k in known})
    return cfg
