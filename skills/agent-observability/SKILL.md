---
name: agent-observability
description: Analyse how AI coding agents are performing from local session logs - token spend, cache hit rate, cost, steps per task, tool loops, tool errors, skill usage, and tokens per commit. Use when the user asks how their agent sessions are going, why sessions are slow or expensive, which model is most effective, whether a skill is being used, to open the agent telemetry dashboard, or to export agent usage data.
---

# Agent observability

The tool lives in the repository root, where `src/agent_observability` is. Run every command from there with `PYTHONPATH=src`. If it's installed with `pip install -e .`, use the `agent-observability` command instead.

## Quick answers: use the summary

```bash
PYTHONPATH=src python3 -m agent_observability.cli --summary --days 30
```

Read it back to the user against these targets:
- **Cache hit:** at least 85%.
- **Average steps per run:** 15 to 35.
- **Healthy sessions:** at least 80%.
- **Tool error rate:** under 1.5%.

Name the biggest gap first.

## Exploring: start the dashboard

```bash
PYTHONPATH=src python3 -m agent_observability.cli --port 8765 --sync-interval 30
```

Give the user `http://127.0.0.1:8765`. Don't bind to `0.0.0.0` unless they ask: the data contains their prompts.

## Data for your own analysis

```bash
PYTHONPATH=src python3 -m agent_observability.cli --export-json /tmp/agents.json --days 180
PYTHONPATH=src python3 -m agent_observability.cli --export-csv /tmp/agent_runs.csv --days 180
```

The JSON has `runs`, `commits`, `kpis`, `breakdowns` and `roi`. Field meanings are in `references/telemetry_schema.md`.

## Turning signals into advice

| Signal | Advice |
| :--- | :--- |
| Many Tool Loops runs, or high loop inflation | Find the repeated command in the inspector (the longest repeat). Suggest adding the correct build or test command to the agent's instructions or a skill, and stopping after two identical failures |
| Wandering: Zero File Writes | The prompts lacked a concrete deliverable. Suggest naming target files, or planning first |
| Low cache hit | Too many short threads or workspace switches. Suggest continuing threads and compacting instead of restarting |
| A skill never appears in Top skills | Its description lacks the words users actually type. Suggest trigger phrases |
| One model has much higher tokens per success | Suggest routing that task type to the more effective model |

## Other agents

Only Claude Code logs are read by default. Any other agent can be added by writing the generic event format in `docs/event-format.md`; `agent_observability.emit.EventLog` writes it from Python. Don't claim data exists for an agent until its events are there.

## Cost caveat

Costs are estimates at API list prices from `pricing.py`. Unknown models are reported as unpriced. On a subscription, present cost as "API-equivalent".
