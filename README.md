# Agent Observability

**Agent Observability** (`agent_observability`) is a zero-dependency Python 3.12+ telemetry collector, analytics engine, CLI and local web dashboard for AI coding agents. It reads your agents' local session logs and the git history of the repositories they worked in. It shows how your agents reason, spend tokens, call tools and load skills, and how that spend turns into shipped code.

It works with any agent:
- **Claude Code** is read out of the box.
- **Any other agent** can appear by writing the [generic event format](docs/event-format.md), or through a small adapter.

Everything stays on your machine. There's no database, no cloud backend and no network calls.

---

## Table of contents

1. [Quick start and CLI](#1-quick-start-and-cli)
2. [Architecture and auto-sync](#2-architecture-and-auto-sync)
3. [Dashboard guide](#3-dashboard-guide)
4. [Engineer's playbook](#4-engineers-playbook)
5. [Adding an agent](#5-adding-an-agent)
6. [Pricing](#6-pricing)
7. [Co-located agent skill](#7-co-located-agent-skill)
8. [Testing](#8-testing)

---

## 1. Quick start and CLI

Run from the project root:

```bash
# Live dashboard on http://127.0.0.1:8765, re-scanning every 30 s
PYTHONPATH=src python3 -m agent_observability.cli --port 8765 --sync-interval 30

# Terminal summary for the last 30 days
PYTHONPATH=src python3 -m agent_observability.cli --summary --days 30

# Export aggregated telemetry (JSON) or one row per task run (CSV)
PYTHONPATH=src python3 -m agent_observability.cli --export-json /tmp/agents.json --days 180
PYTHONPATH=src python3 -m agent_observability.cli --export-csv /tmp/agent_runs.csv --days 180
```

To get an `agent-observability` command instead, run `pip install -e .`. It installs nothing else.

| Option | Default | Meaning |
| :--- | :--- | :--- |
| `--days N` | 180 | How far back to read (0 = everything) |
| `--adapters` | `claude-code,generic` | Which sources to read |
| `--claude-dir` | `~/.claude/projects` | Claude Code transcripts |
| `--events-dir` | `~/.agent-observability/events` | Generic events from any agent |
| `--pricing FILE` | built-in table | Override prices per model (section 6) |
| `--repo PATH` | (none) | Extra git repository to include; repeatable |
| `--author-email E` | your `git config user.email` | Count commits by this email as yours; repeatable |
| `--ai-tag REGEX` | (none) | Extra pattern marking AI-assisted commits, besides `Co-Authored-By` trailers |
| `--no-git`, `--no-cache` | off | Skip git history; skip the on-disk parse cache |
| `--host`, `--port`, `--sync-interval` | `127.0.0.1`, 8765, 30 | Server settings; `--sync-interval 0` turns background sync off |

The server binds to `127.0.0.1`. The data includes your prompts, so don't expose it on a network.

---

## 2. Architecture and auto-sync

```
agent logs ──▶ adapter ──▶ Events ──▶ segment.build_runs ──▶ TaskRun records ──▶ analytics / API / dashboard
git repos  ──▶ git_collector ──▶ Commit records ─────────────────────────────────┘
```

- **Adapters** (`adapters/`) turn one agent's logs into normalized `Event`s: prompt, response, tool call, tool result and title. This is the only agent-specific code.
- **Segmentation** (`segment.py`) groups events into task runs, totals tokens, tools, errors, writes and skills, prices each step, and classifies health.
- **Analytics** (`analytics.py`) computes the KPIs for the CLI and the JSON export. The dashboard computes the same figures in the browser so its filters respond instantly.

| Source | Default path | What's extracted |
| :--- | :--- | :--- |
| Claude Code | `~/.claude/projects/<project>/<session>.jsonl` | Prompts, per-response token usage (input, output, cache read and write, reasoning), model, tool calls and their errors, skills (`Skill` tool, or reads of `*/skills/<name>/SKILL.md`), subagent steps, working directory, title |
| Generic events | `~/.agent-observability/events/**/*.jsonl` | The same fields, written by any agent ([format](docs/event-format.md)) |
| Git history | Repositories found from the sessions' working directories, plus `--repo` | Conventional commit type and scope, linked issues (`#123`, `ABC-123`, `b/123`), your commits, and AI-credited commits (`Co-Authored-By: Claude / Copilot / Gemini / Cursor / Codex…`, or `--ai-tag`) |

### Incremental auto-sync

- **Parse cache:** each log file is cached by size and nanosecond modification time. A sync re-parses only files that changed, so a quiet sync takes milliseconds.
- **Disk cache:** the cache is saved to `~/.cache/agent-observability/runs.json`, so restarting is fast too. Changing prices invalidates it automatically.
- **Two refresh loops:**
  - The server's background thread refreshes its snapshot every `--sync-interval` seconds.
  - The browser polls `/api/telemetry` at the interval you choose (15 s, 30 s, 60 s, 5 min or off), and also when you switch back to the tab.
  - **Sync now** forces an immediate re-scan through `POST /api/sync`.

---

## 3. Dashboard guide

### 3.1 Top bar

- **Mode tabs:**
  - **Agent Observability:** sessions, tokens, models, skills and tool friction.
  - **Code Deliverables:** your local git commits.
  - **Cross-Domain ROI:** agent spend set against commits shipped.
- **Auto-sync and Sync now:** how often the page refreshes, the time of the last sync, and a manual re-scan button.
- **Theme toggle:** dark (the default) or light. Your choice is remembered.

### 3.2 Filter bar

- **Time window:** Today, Last 7 days, Last 30 days or All, or a custom From/To range. It applies to every KPI, chart and table.
- **Granularity:**
  - **Task runs** (default) split each conversation at every prompt (`<id>#1`, `<id>#2`…). Use this to measure what one request costs.
  - **Conversations** merge a whole thread into one record. Use this to measure what a feature cost end to end.
- **Search:** case-insensitive, across run ID, prompt, title, model, workspace, agent, skills and tool names.
- **Agent, model and health outcome filters:** narrow down to one agent, one model or one outcome to see why runs struggled.

### 3.3 KPI cards

| Card | Definition | How to read it |
| :--- | :--- | :--- |
| Total sessions | Task runs (or conversations) in the filter, plus distinct conversations | Overall usage volume |
| Tokens consumed | `input + cache_write + output`; the sub-label shows cache reads, **cache hit %** = `cache_read / (input + cache_write + cache_read)`, and estimated cost | Target cache hit **≥ 85%**: prompt caching is working and input costs fall sharply |
| Average velocity | `steps / sessions`, where a step is one model response | Lower is faster. 15 to 35 steps per run means well-scoped prompts; over 60 suggests broad prompts or retry loops |
| Healthy sessions | Share of runs that are High-Velocity or Positive | Target **≥ 80%**. Below 75%, look at the Tool Loops and High Error Rate slices |
| High velocity rate | Share of runs finishing in **≤ 30 steps with 0 errors** | One-shot efficiency. 50% or more at task-run granularity means prompts and skills lead the agent straight to the right files |
| Tool invocations | Total tool calls, and **tool error rate** = `errors / max(tool_calls, steps)` | Target **< 1.5%**. Spikes usually mean failing builds or tests, missing environment variables, or stale edit targets |

### 3.4 The ten charts

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

### 3.5 Session explorer and inspector

- **Table:** run ID, prompt, agent, model, workspace, steps, tokens, cache hit, tools, skills, health and start time. Click a column to sort.
- **Inspector:** click a row to open it. It shows the full prompt, every tool with its call count, skills, writes and errors, the longest repeat, duration and seconds per step, the token split, estimated cost and cache savings.

### 3.6 Code Deliverables

- **KPIs:** matching commits, your commits, AI-credited commits and linked issues.
- **Charts:** commits by repository, and by conventional commit type.
- **Table:** recent commits.
- **Filters:** the time window and search apply here too.

### 3.7 Cross-Domain ROI

- **KPIs:**
  - Tokens per commit of yours.
  - Agent steps per commit.
  - Estimated cost per commit.
  - Context cache savings: what cached input would have cost at the full input price, minus what it did cost.
  - Issues linked.
- **Chart:** tokens against commits by day.

Sessions and commits are matched by day only. Read it as correlation, not attribution.

---

## 4. Engineer's playbook

| Signal | Likely cause | What to do |
| :--- | :--- | :--- |
| Tool loop inflation above +300% | The agent keeps re-running a failing build or test, or retrying a broken edit | Stop the turn after the same command fails twice. Put the exact test and lint commands in your agent instructions file or a skill |
| Wandering: Zero File Writes runs | An open-ended prompt with no clear deliverable | Name the target files or package in the prompt, or plan first for exploratory work |
| Cache hit below 75% | Many short one-turn conversations, or switching workspaces mid-thread | Keep related work in one thread and workspace. Compact rather than restart when context grows |
| Rare skill activations on common workflows | The agent solves recurring tasks from scratch | Write or refine a skill with explicit trigger phrases in its description |
| Tool error rate above 1.5% | Failing commands, missing environment, stale edit targets | Open the High Error Rate runs in the inspector and fix the commonest failing tool |
| One model has a far higher tokens per success | It loops or wanders more on your work | Route that kind of task to the more effective model |

---

## 5. Adding an agent

There are two ways, and neither touches the analytics.

1. **Write generic events** from the agent, a wrapper or a log converter. See [docs/event-format.md](docs/event-format.md). From Python:

   ```python
   from agent_observability.emit import EventLog
   log = EventLog(agent="My Agent")
   log.prompt("Refactor billing")
   log.response(model="my-model", input=1200, output=300)
   log.tool_call("edit_file", target="billing.py")
   log.tool_result(error=False, chars=420)
   ```

2. **Write an adapter** in `src/agent_observability/adapters/`: a class with `name`, `sources()` (files to read) and `events(path)` (a list of `Event`). Register it in `ADAPTERS`, and add a branch to `make_adapters` in `cli.py`. `claude_code.py` is a complete example in about 100 lines.

---

## 6. Pricing

Costs are **estimates at API list prices**, calculated per response from the model name.

- **Built-in prices:** Anthropic's published rates (input, output, cache read, cache write per million tokens) in `pricing.py`.
- **Subscriptions:** if you're on a flat-rate plan, read cost as "what this would have cost on the API".
- **Unknown models** are shown as unpriced, not guessed.
- **Overrides:** add or override any model, including other vendors' and local ones, with a JSON file:

```json
{"gpt-x": [1.25, 10.0, 0.125, 1.25], "local-llama": [0, 0, 0, 0]}
```

Each value is `[input, output, cache_read, cache_write]` in US dollars per million tokens. Matching is by prefix, so `claude-opus-5-5` covers dated variants. Pass the file with `--pricing prices.json`.

---

## 7. Co-located agent skill

`skills/agent-observability/` is an agent skill. Copy or link it into your agent's skills folder so the agent can run the tool and interpret it for you.

- `SKILL.md`: when to use it, the commands, and how to act on the signals.
- `references/telemetry_schema.md`: the `TaskRun` and `Commit` fields, the health rules, and the HTTP API.
- `evals/evals.json`: trigger and behaviour checks for the skill.

---

## 8. Testing

```bash
python3 -m unittest discover -s tests -v     # standard library only
python3 -m pytest -v                         # also works, if pytest is installed
```

The tests write fixtures to a temporary directory. They never read your real agent logs or touch the network.
