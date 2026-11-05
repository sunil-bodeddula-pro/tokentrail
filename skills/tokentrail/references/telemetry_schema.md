# Telemetry schema

## TaskRun (one per prompt; `runs` in the API and exports)

| Field | Meaning |
| :--- | :--- |
| `run_id` | `<conversation_id>#<n>`: the n-th prompt in the conversation |
| `conversation_id`, `agent`, `machine`, `title` | The conversation, the agent that ran it, the machine whose store it came from, and its title if the agent records one |
| `prompt` | The person's request (first 400 characters). Empty when `redacted` |
| `redacted` | `true` when the run was pulled from a remote that strips prompt text and titles |
| `model`, `models` | Most-used model, and every model used, most-used first. `no response` if the agent never answered |
| `workspace`, `cwd` | Repository name (nearest `.git`), and working directory |
| `started`, `ended` | First and last event time, ISO 8601 UTC |
| `steps`, `subagent_steps` | Model responses, and how many of them ran inside subagents |
| `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `thinking_tokens` | Token usage summed over steps. `input` excludes cached tokens; `output` includes reasoning |
| `prompt_chars`, `tool_output_chars` | Characters of prompt and tool output, for the token anatomy estimate |
| `tools`, `tool_calls`, `tool_errors` | Calls per tool name, total calls, and failed results |
| `file_writes` | Calls to tools whose names contain write, edit, replace, create_file, apply_patch or str_replace |
| `skills` | Skills loaded during the run |
| `max_repeat` | Longest run of identical consecutive tool calls on the same target |
| `health` | One of the five outcomes below |
| `cost_usd`, `cache_savings_usd`, `priced` | Estimated cost, cache savings, and whether every model in the run had a price |

## Health outcomes (checked in this order)

1. **Failure: High Error Rate:** `tool_errors >= 4`, or `steps >= 6` and `tool_errors / max(tool_calls, steps) >= 0.20`.
2. **Friction: Tool Loops:** `max_repeat >= 4`.
3. **Wandering: Zero File Writes:** `steps > 45`, `file_writes == 0` and no skills.
4. **High-Velocity (<=30 steps):** `steps <= 30` and `tool_errors == 0`.
5. **Positive (Standard):** anything else.

High-Velocity and Positive count as healthy.

## Commit (`commits`)

| Field | Meaning |
| :--- | :--- |
| `sha`, `repo`, `author`, `email`, `date`, `subject` | From `git log` |
| `type`, `scope` | Conventional commit type and scope (`feat(api): …`), or empty |
| `issues` | `#123`, `ABC-123` or `b/123` found in the message |
| `ai_tagged` | A `Co-Authored-By` trailer names a known agent, or `--ai-tag` matched |
| `mine` | Author email is yours (`git config user.email`, or `--author-email`) |

## HTTP API

| Method and path | Returns |
| :--- | :--- |
| `GET /api/telemetry` | `{generated, store, health_order, runs, commits}` |
| `POST /api/sync` | Syncs now and returns the same shape |
| `GET /api/health` | `{"ok": true}` |

`store` = `{path, machine, machines, remote, last_sync, last_pull}`. `last_sync` = `{at, files, parsed, unchanged, conversations_changed, repos_changed, pushed, ms}`.

## Store files

`<store>/v1/<machine>/runs/<agent>/<conversation>.json` holds `{agent, conversation_id, machine, source, updated, runs: [TaskRun…]}` for one conversation; `commits/<repo>.json` holds `{repo, machine, updated, commits: [Commit…]}`. The files are plain JSON, safe to read directly.
