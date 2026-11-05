# Contributing to TokenTrail

Thanks for helping. The most useful contributions are adapters for more agents, fixes to how runs are classified, and dashboard improvements.

## Setup

```bash
git clone https://github.com/sunil-bodeddula-pro/tokentrail && cd tokentrail
python3 -m unittest discover -s tests -v        # standard library only; no install needed
PYTHONPATH=src python3 -m tokentrail --config /tmp/tt/config.json --store /tmp/tt/store --port 8765
```

Use a throwaway `--config` and `--store` while developing, so your real store isn't touched.

## Ground rules

- **No new runtime dependencies.** The core runs on the Python standard library. Cloud clients stay optional extras (`[gcs]`, `[s3]`) and are imported only when a remote needs them.
- **Never lose data.** The store only grows: don't add code paths that delete or shrink stored runs.
- **Privacy first.** Anything new that holds user text (prompts, titles, file contents) must be cleared by `mirror.redact` before upload.
- **Tests never touch real logs or the network.** Write fixtures to a temporary directory; fake cloud clients the way `FakeGCS` and `FakeS3` do.
- **Keep the dashboard a single file.** `static/dashboard.html` is vanilla JS with hand-drawn SVG charts and no build step.

## Adding an agent adapter

An adapter turns one agent's log files into `Event`s. It's the only agent-specific code; segmentation, health, pricing, storage and the dashboard work unchanged.

1. Create `src/tokentrail/adapters/<agent>.py` with a class that has:
   - `name`: the agent's display name, for example `"Codex CLI"`.
   - `sources()`: the log files to read (a list of paths). Return an empty list when the agent isn't installed.
   - `events(path)`: a list of `Event` (see `models.py`) for one file, in time order: `PROMPT`, `RESPONSE` (model and token usage), `TOOL_CALL` (tool name and target), `TOOL_RESULT` (error flag and size) and `TITLE`.
2. Register it in `ADAPTERS` in `adapters/__init__.py`, and add a branch to `make_adapters` in `cli.py`.
3. Add a test in `tests/test_telemetry.py` that writes a small fixture log and checks the runs: prompt split, token totals counted once, tool errors and file writes.
4. Add a row to the sources table in the README.

`adapters/claude_code.py` is a complete example. If the agent can't be read directly, it can write the [generic event format](docs/event-format.md) instead, with no adapter at all.

## Pull requests

- Run the tests on Python 3.12 or later.
- For dashboard changes, check desktop and phone widths in both themes, and include a screenshot.
- Keep commits focused and describe the user-visible change.
