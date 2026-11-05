"""Run `tokentrail daemon` in the background at login: systemd (Linux), launchd (macOS), Task Scheduler (Windows)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any

LABEL = "dev.tokentrail.sync"


def _command() -> list[str]:
    return [sys.executable, "-m", "tokentrail", "daemon"]


def _src_dir() -> str | None:
    """When running from a source checkout (not pip-installed), the service needs PYTHONPATH."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return here if os.path.basename(here) == "src" else None


def systemd_unit() -> str:
    env = f"Environment=PYTHONPATH={_src_dir()}\n" if _src_dir() else ""
    return (
        "[Unit]\nDescription=TokenTrail: sync AI agent telemetry\n\n[Service]\n"
        f"ExecStart={' '.join(_command())}\n{env}Restart=on-failure\nRestartSec=30\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def launchd_plist() -> str:
    args = "".join(f"<string>{a}</string>" for a in _command())
    env = (
        f"<key>EnvironmentVariables</key><dict><key>PYTHONPATH</key><string>{_src_dir()}</string></dict>"
        if _src_dir()
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
        f"<key>Label</key><string>{LABEL}</string><key>ProgramArguments</key><array>{args}</array>{env}"
        "<key>RunAtLoad</key><true/><key>KeepAlive</key><true/></dict></plist>\n"
    )


def windows_command() -> str:
    return f'schtasks /Create /SC ONLOGON /TN TokenTrail /TR "{" ".join(_command())}" /F'


def paths() -> dict[str, Any]:
    return {
        "Linux": os.path.expanduser("~/.config/systemd/user/tokentrail.service"),
        "Darwin": os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist"),
    }


def describe() -> str:
    system = platform.system()
    if system == "Linux":
        then = "systemctl --user daemon-reload && systemctl --user enable --now tokentrail"
        return f"# {paths()['Linux']}\n{systemd_unit()}\n# then: {then}"
    if system == "Darwin":
        return f"# {paths()['Darwin']}\n{launchd_plist()}\n# then: launchctl load -w {paths()['Darwin']}"
    return f"# run in a terminal:\n{windows_command()}"


def install() -> str:
    system = platform.system()
    if system == "Linux":
        path = paths()["Linux"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(systemd_unit())
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", "tokentrail"], check=False)
        return f"Installed {path} and started it (systemctl --user status tokentrail)."
    if system == "Darwin":
        path = paths()["Darwin"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(launchd_plist())
        subprocess.run(["launchctl", "load", "-w", path], check=False)
        return f"Installed {path} and loaded it."
    subprocess.run(windows_command(), shell=True, check=False)
    return "Registered the TokenTrail task to start at logon."


def uninstall() -> str:
    system = platform.system()
    if system == "Linux":
        subprocess.run(["systemctl", "--user", "disable", "--now", "tokentrail"], check=False)
        if os.path.exists(paths()["Linux"]):
            os.remove(paths()["Linux"])
        return "Stopped and removed the TokenTrail service. Your store is untouched."
    if system == "Darwin":
        path = paths()["Darwin"]
        subprocess.run(["launchctl", "unload", "-w", path], check=False)
        if os.path.exists(path):
            os.remove(path)
        return "Unloaded and removed the TokenTrail agent. Your store is untouched."
    subprocess.run("schtasks /Delete /TN TokenTrail /F", shell=True, check=False)
    return "Removed the TokenTrail task. Your store is untouched."
