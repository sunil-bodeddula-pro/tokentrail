# TokenTrail

[![CI](https://github.com/sunil-bodeddula-pro/tokentrail/actions/workflows/ci.yml/badge.svg)](https://github.com/sunil-bodeddula-pro/tokentrail/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tokentrail.svg)](https://pypi.org/project/tokentrail/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**See what your AI agents actually do with your tokens.** TokenTrail is local-first observability for AI agents. It shows how they spend tokens, call tools and load skills, where they get stuck, and how all of that turns into shipped code. It runs on your own machine.

![The TokenTrail dashboard: six KPI cards (sessions, tokens, velocity, healthy share, high-velocity rate, tool calls) above the chart grid, with demo data](docs/images/overview.png)

<sub>All screenshots use the [demo data](#try-it-with-demo-data), not real sessions.</sub>

## Why TokenTrail?

AI coding agents now do a lot of real work, but most of it happens out of sight. A session runs for twenty minutes, burns half a million tokens, and you only see the final answer. Was it efficient? Did it loop on a failing test? Did it ever use the skill you wrote for exactly this task? Is the expensive model worth it for this kind of work? And when the agent's history is cleared, the evidence is gone too.

TokenTrail answers those questions from data your agents already leave on disk, without changing how you work.

## What it does

1. **Collects** each agent's local session logs as they're written. Claude Code works out of the box, and any other agent can write a simple [JSON-lines event format](docs/event-format.md).
2. **Keeps its own record** in a store of plain JSON files, synced every 30 seconds. Clearing an agent's history loses nothing, and nothing is parsed twice.
3. **Measures every request:** tokens (input, output, cache reads and writes, reasoning), cache hit rate, estimated cost, steps, tool calls and errors, file writes, skills and subagents.
4. **Classifies each run's health:** High-Velocity, Positive, Tool Loops, Wandering (lots of steps, nothing written) or High Error Rate. You can see at a glance which requests went well and which didn't.
5. **Connects agent work to shipped code** by reading the git history of the repositories the agents worked in: your commits, AI-credited commits, linked issues, and tokens and cost per commit.
6. **Shows it all on a local dashboard,** with filters by time, agent, model, outcome and machine, ten charts, a searchable session table, and an inspector for every run.
7. **Optionally mirrors the store** to Google Cloud Storage, S3 or a shared folder, so you can see several machines in one place. Prompt text is removed before upload.

## Questions it answers

| Question | Where to look |
| :--- | :--- |
| How much are my agents costing me, and is prompt caching working? | Tokens consumed card (cache hit %, estimated cost), Token anatomy |
| Which requests went badly, and why? | Session health chart, the Health filter, the inspector (longest repeat, errors, writes) |
| Is the agent stuck in a loop re-running the same failing command? | Tool Loops outcome, Outcome token waste ("tool loop inflation") |
| Which model gets my kind of work done for the fewest tokens? | Token spend vs task effectiveness (tokens per successful run, by model) |
| Are my skills and agent instructions being used? | Top skills activated |
| Is the agent reading sensibly, or dumping whole files and logs? | Tool invocation frequency (read-to-edit ratio), Token anatomy (tool output share) |
| Which repositories take the most agent time? | Workspace distribution and turn latency |
| What does a commit cost me in agent tokens and dollars? | Cross-Domain ROI |

## Who it helps

- **Developers using AI agents every day** can tighten prompts, catch loops early, keep cache hit rates high, and pick the right model for each job.
- **Authors of skills, agent instructions and custom agents** can check whether their skills fire and whether a change made runs faster or slower.
- **Team leads and platform teams** can mirror several machines into one bucket and see usage, cost and health across the team, with prompts redacted.
- **Anyone curious about cost** gets an API-equivalent estimate per run, per model and per commit, even on a flat-rate plan.

## What it isn't

- **Not a cloud service.** There's no account and no backend. Data stays on your machine unless you configure a remote.
- **Not a tracing SDK for production LLM apps.** It watches agents you run, from their logs, with no code changes. To trace an application you're deploying, use an APM or LLM tracing tool.
- **It doesn't call any model.** Analysis is plain counting, so using TokenTrail costs no tokens.
- **Costs are estimates** at API list prices, not your invoice.

## Screenshots

| | |
| :---: | :---: |
| ![Charts: session health donut, top skills, tool frequency and model step velocity](docs/images/charts.png) | ![Session inspector for a run flagged as a tool loop: tokens, tools, longest repeat, duration and cost](docs/images/inspector.png) |
| **Health, skills, tools and velocity.** Ten charts in all, grouped by tokens, effectiveness, time and tools. | **The inspector.** One run flagged as a tool loop: the same command repeated six times. |
| ![Cross-Domain ROI: tokens and agent steps per commit, cost per commit, cache savings, linked issues](docs/images/roi.png) | |
| **Cross-Domain ROI.** Agent tokens, steps and cost per commit, and what caching saved. | |

## Try it with demo data

No agent needed. The demo script writes a month of made-up sessions for three agents and four small git repositories into one folder. Your real history and store aren't touched.

```bash
git clone https://github.com/sunil-bodeddula-pro/tokentrail && cd tokentrail
python3 examples/demo_data.py                                   # writes ./tokentrail-demo
PYTHONPATH=src python3 -m tokentrail --config tokentrail-demo/config.json
```

Then open http://127.0.0.1:8765. Delete the `tokentrail-demo` folder when you're done.

---

## Table of contents

1. [Install and quick start](#1-install-and-quick-start)
2. [Commands and settings](#2-commands-and-settings)
3. [The store, remote mirrors and privacy](#3-the-store-remote-mirrors-and-privacy)
4. [Architecture](#4-architecture)
5. [Dashboard guide](#5-dashboard-guide)
6. [Engineer's playbook](#6-engineers-playbook)
7. [Adding an agent](#7-adding-an-agent)
8. [Pricing](#8-pricing)
9. [Co-located agent skill](#9-co-located-agent-skill)
10. [Testing and contributing](#10-testing-and-contributing)

---

## 1. Install and quick start

```bash
pip install tokentrail              # or: pipx install tokentrail
pip install 'tokentrail[gcs]'       # add Google Cloud Storage support
pip install 'tokentrail[s3]'        # add AWS S3 (and S3-compatible) support

tokentrail init                     # choose the store folder and an optional remote; runs the first sync
tokentrail                          # open the dashboard at http://127.0.0.1:8765 (it keeps syncing while open)
tokentrail service install          # optional: keep syncing in the background at login
```

From a source checkout, run `pip install -e .` or use `PYTHONPATH=src python3 -m tokentrail …`.

`tokentrail init` asks three questions; `--yes` accepts the defaults:

| Question | Default |
| :--- | :--- |
| Local store folder | `~/.tokentrail/store` |
| Remote mirror | none (`gs://bucket/path`, `s3://bucket/path`, or a folder) |
| Seconds between syncs | 30 |

---

## 2. Commands and settings

| Command | What it does |
| :--- | :--- |
| `tokentrail init` | Save settings, check the remote is reachable, run the first sync. `--service` also installs the background service; `--keep-prompts-remote` uploads prompt text too |
| `tokentrail` or `tokentrail dashboard` | Pull other machines' data, sync, and serve the dashboard. `--port`, `--host`, `--sync-interval SECONDS` (0 = read the store only) |
| `tokentrail daemon` | Sync on a timer with no dashboard. This is what the service runs |
| `tokentrail sync` | Sync once and exit |
| `tokentrail pull` | Download other machines' data from the remote, and restore any of this machine's files missing locally |
| `tokentrail status` | Where data lives, how much there is, which machines, when it last synced |
| `tokentrail summary --days 30` | Headline numbers in the terminal |
| `tokentrail export --json F --csv F` | Everything as JSON (runs, commits, KPIs, breakdowns, ROI), or one CSV row per task run |
| `tokentrail service install \| uninstall \| print` | Run `daemon` at login: a systemd user unit (Linux), a launchd agent (macOS) or a Task Scheduler task (Windows). `print` shows what would be installed |

**Sync interval:** `--sync-interval SECONDS` (or `--interval`) on `init`, `dashboard` and `daemon` sets how often TokenTrail syncs, for example `tokentrail --port 8765 --sync-interval 60`. Without it, the `sync_interval` setting is used, which is 30 seconds unless you changed it. With `init`, the value is saved to the config. The dashboard page refreshes at the same interval until you pick another one in its Auto-sync menu.

Options that work with every command except `service`: `--config FILE`, `--store DIR`, `--remote URI`, `--no-remote`, `--days N` (0 = everything) and `--no-git`.

Settings live in `~/.config/tokentrail/config.json` (`%APPDATA%\tokentrail\config.json` on Windows; `TOKENTRAIL_CONFIG` points elsewhere). Command-line options win over the file.

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `store` | `~/.tokentrail/store` | The local store, the system of record |
| `remote` | `""` | Optional mirror: `gs://…`, `s3://…`, `file://…` or a folder path |
| `redact_remote` | `true` | Remove prompt text and titles before upload |
| `sync_interval` | 30 | Seconds between syncs |
| `machine_id` | `""` | Blank: a stable name, your hostname plus four hex characters, is created and kept in `<store>/.machine-id` |
| `adapters` | `["claude-code", "generic"]` | Which sources to read |
| `claude_dir` | `~/.claude/projects` | Claude Code transcripts |
| `events_dir` | `~/.tokentrail/events` | Generic events from any agent |
| `pricing` | `""` | JSON file overriding prices per model ([Pricing](#8-pricing)) |
| `repos` | `[]` | Extra git repositories to include, besides those the agents worked in |
| `author_emails` | `[]` | Count commits by these emails as yours (default: `git config user.email`) |
| `ai_tag` | `""` | Extra regex marking AI-assisted commits, besides `Co-Authored-By` trailers |
| `git_days` | 365 | How much git history to read |

---

## 3. The store, remote mirrors and privacy

### The store

The store is a folder of plain JSON files. There is one file per conversation, written atomically (to a temporary file, then renamed into place):

```
~/.tokentrail/store/
  .machine-id                      this machine's name
  .mirror-state.json               what has been uploaded and downloaded (never uploaded)
  v1/<machine>/
    runs/<agent>/<conversation>.json   the task runs of one conversation
    commits/<repo>.json                commits from that repository
    manifest.json                      counts and the last sync time
    sources.json                       which agent files have been read, by size and mtime (never uploaded)
  v1/<other-machine>/…                 pulled from the remote
```

- **Incremental:** a sync re-reads an agent file only when its size or modification time changes, or when prices change. A quiet sync takes milliseconds and costs no tokens; TokenTrail never calls a model.
- **Never deletes:** when an agent's history file disappears, its conversations stay in the store. When a file shrinks, the stored runs and the new runs are merged, so nothing is lost.
- **Git** is re-read every five minutes, not every sync, and commits are merged by SHA.

### Remote mirrors

| Remote | Needs | Credentials |
| :--- | :--- | :--- |
| `gs://bucket/prefix` | `pip install 'tokentrail[gcs]'` | Application Default Credentials (`gcloud auth application-default login`, or a service account) |
| `s3://bucket/prefix` | `pip install 'tokentrail[s3]'` | The usual AWS chain (`AWS_PROFILE`, environment variables, SSO, instance roles). For MinIO, Cloudflare R2 and other S3-compatible stores, set `AWS_ENDPOINT_URL` |
| `file:///path` or a path | nothing | A network drive or a synced folder |

- **Push:** after each sync, this machine's changed files are uploaded. Files are compared by MD5, so an unchanged file is never sent twice.
- **Pull:** when the dashboard starts, and every five minutes while it runs, other machines' new files are downloaded. Each machine writes only under its own `v1/<machine>/` prefix, so machines never overwrite each other.
- **Restore:** `tokentrail pull` on a machine whose store was wiped brings its files back from the remote. They come back redacted if they were uploaded redacted.

### Privacy

- **Local only by default.** The dashboard binds to `127.0.0.1`. Your prompts are in the data, so don't expose the dashboard on a network.
- **Redacted remotes.** With `redact_remote` on (the default), the `prompt` and `title` of every run are emptied before upload, and the run is marked `redacted`. Token counts, tool names, models, workspaces and timings are still uploaded.
- **Use a private bucket.** Workspace and repository names, commit subjects and author emails are not redacted.
- **No telemetry about you.** TokenTrail makes no network calls except to the remote you configure.

---

## 4. Architecture

```
agent logs ──▶ adapter ──▶ Events ──▶ segment.build_runs ──▶ TaskRun records ──┐
git repos  ──▶ git_collector ──▶ Commit records ───────────────────────────────┤
                                                                               ▼
                         Syncer (every 30 s) ──▶ Store (JSON files) ◀──▶ Mirror (gs:// · s3:// · folder)
                                                      │
                                                      ▼
                                 TelemetryState ──▶ HTTP API ──▶ dashboard, summary, export
```

- **Adapters** (`adapters/`) turn one agent's logs into normalized `Event`s: prompt, response, tool call, tool result and title. This is the only agent-specific code.
- **Segmentation** (`segment.py`) groups events into task runs, totals tokens, tools, errors, writes and skills, prices each step, and classifies health.
- **Syncer, Store and Mirror** (`sync.py`, `store.py`, `mirror.py`) keep the durable record described above.
- **Analytics** (`analytics.py`) computes the KPIs for the CLI and the JSON export. The dashboard computes the same figures in the browser, so its filters respond instantly.

| Source | Default path | What's extracted |
| :--- | :--- | :--- |
| Claude Code | `~/.claude/projects/<project>/<session>.jsonl` | Prompts, per-response token usage (input, output, cache read and write, reasoning), model, tool calls and their errors, skills (`Skill` tool, or reads of `*/skills/<name>/SKILL.md`), subagent steps, working directory, title |
| Generic events | `~/.tokentrail/events/**/*.jsonl` | The same fields, written by any agent ([format](docs/event-format.md)) |
| Git history | Repositories found from the sessions' working directories, plus `repos` | Conventional commit type and scope, linked issues (`#123`, `ABC-123`, `b/123`), your commits, and AI-credited commits (`Co-Authored-By: Claude / Copilot / Gemini / Cursor / Codex…`, or `ai_tag`) |

The browser polls `/api/telemetry` at the interval you choose (15 s, 30 s, 60 s, 5 min or off), and again when you switch back to the tab. **Sync now** forces an immediate sync through `POST /api/sync`.

---

## 5. Dashboard guide

### 5.1 Top bar

- **Mode tabs:**
  - **TokenTrail:** sessions, tokens, models, skills and tool friction.
  - **Code Deliverables:** your local git commits.
  - **Cross-Domain ROI:** agent spend set against commits shipped.
- **Auto-sync and Sync now:** how often the page refreshes, the time of the last sync, and a manual re-scan button.
- **Theme toggle:** dark (the default) or light. Your choice is remembered.

### 5.2 Filter bar

- **Time window:** Today, Last 7 days, Last 30 days or All, or a custom From/To range. It applies to every KPI, chart and table.
- **Granularity:**
  - **Task runs** (default) split each conversation at every prompt (`<id>#1`, `<id>#2`…). Use this to measure what one request costs.
  - **Conversations** merge a whole thread into one record. Use this to measure what a feature cost end to end.
- **Search:** case-insensitive, across run ID, prompt, title, model, workspace, agent, skills and tool names.
- **Agent, model and health outcome filters:** narrow down to one agent, one model or one outcome to see why runs struggled.
- **Machine filter:** appears when the store holds more than one machine's data.
- **Store line:** under the top bar, the store path, this machine's name, the remote and the last sync.

### 5.3 KPI cards

| Card | Definition | How to read it |
| :--- | :--- | :--- |
| Total sessions | Task runs (or conversations) in the filter, plus distinct conversations | Overall usage volume |
| Tokens consumed | `input + cache_write + output`; the sub-label shows cache reads, **cache hit %** = `cache_read / (input + cache_write + cache_read)`, and estimated cost | Target cache hit **≥ 85%**: prompt caching is working and input costs fall sharply |
| Average velocity | `steps / sessions`, where a step is one model response | Lower is faster. 15 to 35 steps per run means well-scoped prompts; over 60 suggests broad prompts or retry loops |
| Healthy sessions | Share of runs that are High-Velocity or Positive | Target **≥ 80%**. Below 75%, look at the Tool Loops and High Error Rate slices |
| High velocity rate | Share of runs finishing in **≤ 30 steps with 0 errors** | One-shot efficiency. 50% or more at task-run granularity means prompts and skills lead the agent straight to the right files |
| Tool invocations | Total tool calls, and **tool error rate** = `errors / max(tool_calls, steps)` | Target **< 1.5%**. Spikes usually mean failing builds or tests, missing environment variables, or stale edit targets |

### 5.4 The ten charts

Chart sub-tabs filter them: All (10), Tokens (4), Effectiveness (4), Time and latency (3), Tools and skills (3).

1. **Model utilization** (donut): share of sessions per model. Check that light work runs on fast models and hard work on strong ones.
2. **Token anatomy** (donut): new context split into **tool outputs**, **model reasoning**, **model responses** and **user instructions**. Tool outputs and prompts are estimated at 4 characters per token. When tool outputs dominate (often over 90%), prefer targeted searches and line-bounded reads over dumping whole files or logs.
3. **Session health and friction** (donut): the five mutually exclusive outcomes, checked in this order.

   | Outcome | Rule |
   | :--- | :--- |
   | Failure: High Error Rate | ≥ 4 tool errors, or an error rate ≥ 20% with ≥ 6 steps |
   | Friction: Tool Loops | ≥ 4 identical consecutive tool calls on the same target |
   | Wandering: Zero File Writes | > 45 steps with no file writes and no skills |
   | High-Velocity (≤30 steps) | ≤ 30 steps and 0 errors |
   | Positive (Standard) | Everything else: clean, longer runs |

4. **Top skills activated** (bars): skills the agent loaded. If a skill you wrote never appears, sharpen the trigger words in its description.
5. **Tool invocation frequency** (bars), with the read-to-edit ratio. Healthy is about 3:1 to 5:1. If a shell tool dwarfs reads and edits by 10:1, the agent is probably using shell commands to view files or polling in a loop.
6. **Model step velocity** (bars): average steps per run by model. Lower finishes faster.
7. **Token spend vs task effectiveness** (bars and line): average tokens per run, **tokens per healthy run**, and success rate by model, with the most effective model named. Tokens per success is the real efficiency measure: a model that costs more per run but rarely loops often costs less per solved task.
8. **Outcome token waste** (bars): average tokens per outcome, with a **Tool loop inflation** banner showing extra tokens burned by looping runs compared with clean ones.
9. **Daily activity and token volume** (wide): sessions per day for the last 14 active days, with tokens as a line.
10. **Workspace distribution and turn latency** (wide): sessions per repository, with average steps and seconds per step.

### 5.5 Session explorer and inspector

- **Table:** run ID, prompt, agent, model, workspace, steps, tokens, cache hit, tools, skills, health and start time. Click a column to sort. Rows are split into pages, with 10, 25, 50 or 100 per page (25 by default, and your choice is remembered). Changing a filter, the search or the sort goes back to page 1; background syncs keep your page.
- **Inspector:** click a row to open it. It shows the machine, the full prompt (or "redacted" for runs pulled from a redacted remote), every tool with its call count, skills, writes and errors, the longest repeat, duration and seconds per step, the token split, estimated cost and cache savings.

### 5.6 Code Deliverables

- **KPIs:** matching commits, your commits, AI-credited commits and linked issues.
- **Charts:** commits by repository, and by conventional commit type.
- **Table:** recent commits.
- **Filters:** the time window and search apply here too.

### 5.7 Cross-Domain ROI

- **KPIs:**
  - Tokens per commit of yours.
  - Agent steps per commit.
  - Estimated cost per commit.
  - Context cache savings: what cached input would have cost at the full input price, minus what it did cost.
  - Issues linked.
- **Chart:** tokens against commits by day.

Sessions and commits are matched by day only. Read it as correlation, not attribution.

---

## 6. Engineer's playbook

| Signal | Likely cause | What to do |
| :--- | :--- | :--- |
| Tool loop inflation above +300% | The agent keeps re-running a failing build or test, or retrying a broken edit | Stop the turn after the same command fails twice. Put the exact test and lint commands in your agent instructions file or a skill |
| Wandering: Zero File Writes runs | An open-ended prompt with no clear deliverable | Name the target files or package in the prompt, or plan first for exploratory work |
| Cache hit below 75% | Many short one-turn conversations, or switching workspaces mid-thread | Keep related work in one thread and workspace. Compact rather than restart when context grows |
| Rare skill activations on common workflows | The agent solves recurring tasks from scratch | Write or refine a skill with explicit trigger phrases in its description |
| Tool error rate above 1.5% | Failing commands, missing environment, stale edit targets | Open the High Error Rate runs in the inspector and fix the commonest failing tool |
| One model has a far higher tokens per success | It loops or wanders more on your work | Route that kind of task to the more effective model |

---

## 7. Adding an agent

There are two ways, and neither touches the analytics.

1. **Write generic events** from the agent, a wrapper or a log converter. See [docs/event-format.md](docs/event-format.md). From Python:

   ```python
   from tokentrail.emit import EventLog

   log = EventLog(agent="My Agent")
   log.prompt("Refactor billing")
   log.response(model="my-model", input=1200, output=300)
   log.tool_call("edit_file", target="billing.py")
   log.tool_result(error=False, chars=420)
   ```

2. **Write an adapter** in `src/tokentrail/adapters/`: a class with `name`, `sources()` (files to read) and `events(path)` (a list of `Event`). Register it in `ADAPTERS`, add a branch to `make_adapters` in `cli.py`, and add a fixture test. [CONTRIBUTING.md](CONTRIBUTING.md) walks through it. `claude_code.py` is a complete example in about 100 lines.

---

## 8. Pricing

Costs are **estimates at API list prices**, calculated per response from the model name.

- **Built-in prices:** Anthropic's published rates (input, output, cache read, cache write per million tokens) in `pricing.py`.
- **Subscriptions:** if you're on a flat-rate plan, read cost as "what this would have cost on the API".
- **Unknown models** are shown as unpriced, not guessed.
- **Overrides:** add or override any model, including other vendors' and local ones, with a JSON file:

```json
{"gpt-x": [1.25, 10.0, 0.125, 1.25], "local-llama": [0, 0, 0, 0]}
```

Each value is `[input, output, cache_read, cache_write]` in US dollars per million tokens. Matching is by prefix, so `claude-opus-5-5` covers dated variants. Point the `pricing` setting at the file. Changing prices re-prices every agent file that still exists on the next sync; conversations whose source file is gone keep the prices they were stored with.

---

## 9. Co-located agent skill

`skills/tokentrail/` is an agent skill. Copy or link it into your agent's skills folder so the agent can run the tool and interpret it for you.

- `SKILL.md`: when to use it, the commands, and how to act on the signals.
- `references/telemetry_schema.md`: the `TaskRun` and `Commit` fields, the health rules, and the HTTP API.
- `evals/evals.json`: trigger and behaviour checks for the skill.

---

## 10. Testing and contributing

```bash
python3 -m unittest discover -s tests -v     # standard library only
python3 -m pytest -v                         # also works, if pytest is installed
```

Lint, formatting and strict type checks, as CI runs them:

```bash
pip install -e '.[dev]'                      # ruff and mypy
ruff check . && ruff format --check . && mypy
```

The tests write fixtures to a temporary directory. They never read your real agent logs or touch the network: the GCS and S3 backends are tested against in-memory fakes.

Contributions are welcome, especially adapters for other agents. See [CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md) for reporting a vulnerability.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
