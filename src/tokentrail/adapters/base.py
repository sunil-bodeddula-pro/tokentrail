from __future__ import annotations

import glob
import os
from typing import Protocol

from ..models import Event


class Adapter(Protocol):
    name: str

    def sources(self) -> list[str]: ...

    def events(self, path: str) -> list[Event]: ...


def find_files(root: str, pattern: str) -> list[str]:
    """Files under root matching a glob pattern, or nothing if root doesn't exist."""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return []
    return sorted(glob.glob(os.path.join(root, pattern), recursive=True))


def target_of(tool_input: object) -> str:
    """The thing a tool acted on, used to spot loops (the same call on the same target again and again)."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("file_path", "path", "notebook_path", "command", "pattern", "query", "url", "skill"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value[:300]
    return ""
