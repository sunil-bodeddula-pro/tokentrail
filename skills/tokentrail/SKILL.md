---
name: tokentrail
description: Analyse how AI coding agents are performing from local session logs - token spend, cache hit rate, cost, steps per task, tool loops, tool errors, skill usage, and tokens per commit. Use when the user asks how their agent sessions are going, why sessions are slow or expensive, which model is most effective, whether a skill is being used, to open the agent telemetry dashboard, or to export agent usage data.
---

# Agent observability

Use the `tokentrail` command if it's installed (`pip install tokentrail`). From a source checkout, run `PYTHONPATH=src python3 -m tokentrail` from the repository root instead.

## First run

If `tokentrail status` says the config isn't created yet, tell the user what `tokentrail init` does before running it: it creates a local store (`~/.tokentrail/store` by default), can mirror it to a bucket, and runs the first sync. Ask before adding a remote, and never run `tokentrail service install` without the user's say-so: it starts a background process at login.

## Quick answers: use the summary

```bash
tokentrail summary --days 30
```

Read it back to the user against these targets:
- **Cache hit:** at least 85%.
- **Average steps per run:** 15 to 35.
- **Healthy sessions:** at least 80%.
- **Tool error rate:** under 1.5%.

Name the biggest gap first.

## Exploring: start the dashboard

```bash
tokentrail dashboard --port 8765
```

Give the user `http://127.0.0.1:8765`. Don't pass `--host 0.0.0.0` unless they ask: the data contains their prompts.

## Where the data is and whether it's fresh

```bash
tokentrail status
```

It shows the store path, the machines in it, the remote, and the last sync. Data is read from the store, not from the agent's history, so conversations stay after the history is cleared. Runs pulled from a redacted remote have empty prompts and `redacted: true`; don't present them as missing data.

## Data for your own analysis

```bash
tokentrail export --json /tmp/agents.json --days 180
tokentrail export --csv /tmp/agent_runs.csv --days 180
```

The JSON has `store`, `runs`, `commits`, `kpis`, `breakdowns` and `roi`. Field meanings are in `references/telemetry_schema.md`. To answer questions without spending tokens on raw logs, read the export or the store's JSON files, never the agent transcripts.

## Turning signals into advice

| Signal | Advice |
| :--- | :--- |
| Many Tool Loops runs, or high loop inflation | Find the repeated command in the inspector (the longest repeat). Suggest adding the correct build or test command to the agent's instructions or a skill, and stopping after two identical failures |
| Wandering: Zero File Writes | The prompts lacked a concrete deliverable. Suggest naming target files, or planning first |
| Low cache hit | Too many short threads or workspace switches. Suggest continuing threads and compacting instead of restarting |
| A skill never appears in Top skills | Its description lacks the words users actually type. Suggest trigger phrases |
| One model has much higher tokens per success | Suggest routing that task type to the more effective model |

## Other agents

Only Claude Code logs are read by default. Any other agent can be added by writing the generic event format in `docs/event-format.md`; `tokentrail.emit.EventLog` writes it from Python. Don't claim data exists for an agent until its events are there.

## Cost caveat

Costs are estimates at API list prices from `pricing.py`, or the user's `pricing` override file. Unknown models are reported as unpriced. On a subscription, present cost as "API-equivalent".
