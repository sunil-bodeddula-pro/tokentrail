# AGENTS.md

Instructions for AI coding agents (Claude Code, Codex, Cursor, Copilot and others) working on this repository. People should read [CONTRIBUTING.md](CONTRIBUTING.md); this file is the short version, plus what an agent tends to get wrong.

## What this is

TokenTrail reads AI agents' local session logs, keeps its own durable copy in a store of plain JSON files, optionally mirrors it to `gs://`, `s3://` or a folder, and serves a local dashboard. Python 3.12+, **standard library only** at runtime.

## Commands

```bash
python3 -m unittest discover -s tests -v              # tests: standard library only, no install needed
pip install -e '.[dev]'                               # ruff and mypy, once
ruff check . && ruff format --check . && mypy         # lint, formatting, strict types: CI runs all three
ruff check --fix . && ruff format .                   # fix what can be fixed automatically
PYTHONPATH=src python3 -m tokentrail --config /tmp/tt/config.json --store /tmp/tt/store --port 8765
```

Before you say a change is done, run the tests, `ruff check .`, `ruff format --check .` and `mypy`, and report the results honestly.

## Layout

| Path | What it is |
| :--- | :--- |
| `src/tokentrail/adapters/` | One adapter per agent: log files → `Event`s. The only agent-specific code |
| `src/tokentrail/models.py` | `Event`, `Kind`, `TaskRun`, `Commit`, `Health` |
| `src/tokentrail/segment.py` | Events → task runs, totals, pricing, the health rules |
| `src/tokentrail/store.py`, `sync.py`, `mirror.py` | The durable store, the incremental sync, the remote mirror |
| `src/tokentrail/state.py`, `server.py` | What the dashboard serves, and the HTTP API |
| `src/tokentrail/cli.py`, `config.py`, `service.py` | Commands, settings, the login service |
| `src/tokentrail/static/dashboard.html` | The whole dashboard: one file, vanilla JS, hand-drawn SVG charts |
| `skills/tokentrail/` | The agent skill shipped to users (how to run and read TokenTrail), not instructions for this repo |
| `docs/event-format.md` | The generic event format any agent can write |
| `tests/test_telemetry.py` | All tests, with fixtures written to temp dirs and in-memory fakes for GCS and S3 |

## Rules

- **No runtime dependencies.** Don't add imports outside the standard library to `src/`. Cloud clients (`google-cloud-storage`, `boto3`) are optional extras, imported lazily inside `mirror.py` only.
- **Never lose user data.** The store only adds and updates. Don't write code that deletes stored runs or shrinks a conversation file; `Store.upsert_conversation` merges when a source file shrinks.
- **Privacy.** Any new field holding user text (prompts, titles, file contents, tool output) must be cleared by `mirror.redact` before upload. The server binds to `127.0.0.1`; keep that the default.
- **Don't read the user's real data in tests.** Never point tests at `~/.claude` or a real store, and never touch the network. Fake cloud clients the way `FakeGCS` and `FakeS3` do.
- **Keep the store format stable.** Files live under `v1/`. A breaking change to their shape needs a new format directory and a migration, not an in-place change.
- **Health rules and KPI definitions are documented** in the README, `skills/tokentrail/references/telemetry_schema.md` and the dashboard's chart captions. Change all of them together.
- **Typed code.** mypy runs in strict mode: annotate every function. Use `dict[str, Any]` for JSON records and the `Adapter` and `Backend` protocols, not concrete classes.
- **Dashboard changes** must work at phone width (no sideways scroll) and in both themes.
- **Don't install the background service** (`tokentrail service install`) or write to `~/.config/tokentrail` on the user's machine while developing. Use `--config` and `--store` pointing at a temp folder.

## Adding an agent

See "Adding an agent adapter" in [CONTRIBUTING.md](CONTRIBUTING.md): an adapter class with `name`, `sources()` and `events(path)`, registered in `adapters/__init__.py` and `cli.make_adapters`, plus a fixture test and a README row.

## Style

- Match the surrounding code: short docstrings that say why, comments only where the reason isn't obvious.
- Line length 120. Ruff formats; don't hand-format against it.
- In the docs, plain English, short sentences, tables for reference material.
