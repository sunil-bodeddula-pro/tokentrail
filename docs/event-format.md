# Generic event format

Any agent can appear in the dashboard by writing this format. No code changes to the tool are needed.

- **Where:** `*.jsonl` files under `~/.tokentrail/events/`, any depth (change it with `events_dir` in the config file). One file per session is simplest; never split one session across files.
- **What:** one JSON object per line, in time order. Unknown fields are ignored. Lines with an unknown `event` or no `session_id` are skipped.
- **From Python:** `tokentrail.emit.EventLog` writes it for you.

## Fields

| Field | Type | Events | Meaning |
| :--- | :--- | :--- | :--- |
| `event` | string | all | `prompt`, `response`, `tool_call`, `tool_result` or `title` |
| `session_id` | string | all | One conversation or agent run. Task runs are numbered `<session_id>#1`, `#2`… |
| `ts` | ISO 8601 | all | When it happened, preferably UTC with `Z` |
| `agent` | string | any | Agent name shown in the dashboard (defaults to `Generic`) |
| `workspace` | path | any | Working directory; used for the Workspace column and to find git repositories |
| `text` | string | `prompt`, `title` | The person's request (first 400 characters kept), or the conversation title |
| `chars` | int | `prompt`, `tool_result` | Length of the prompt or tool output, for the token anatomy chart |
| `model` | string | `response` | Model name; also selects the price (see Pricing in the README) |
| `message_id` | string | `response` | De-duplicates a response logged in several pieces |
| `usage` | object | `response` | `input`, `output`, `cache_read`, `cache_write`, `thinking` token counts. `input` excludes cached tokens; `output` includes `thinking` |
| `tool` | string | `tool_call` | Tool name. Names containing write, edit, replace, create_file or apply_patch count as file writes |
| `target` | string | `tool_call` | File, command or query the tool acted on; four identical calls in a row mark a tool loop |
| `skill` | string | `tool_call` | Skill or playbook the call loaded, for the Top skills chart |
| `tool_id` | string | `tool_call`, `tool_result` | Pairs a result with its call (optional) |
| `error` | bool | `tool_result` | The tool failed |
| `subagent` | bool | any | The event happened inside a subagent |

## Rules the analytics apply

- A `prompt` starts a new task run; everything until the next `prompt` belongs to it.
- Each `response` is one step.
- Tokens consumed are `input + cache_write + output`.
- The cache hit rate is `cache_read / (input + cache_write + cache_read)`.

## Example

```json
{"event": "prompt", "session_id": "r42", "agent": "Release Bot", "ts": "2026-11-04T09:00:00Z", "workspace": "/src/shop", "text": "Bump the API version", "chars": 20}
{"event": "response", "session_id": "r42", "ts": "2026-11-04T09:00:03Z", "model": "claude-sonnet-5-5", "message_id": "a1", "usage": {"input": 1200, "output": 240, "cache_read": 18000}}
{"event": "tool_call", "session_id": "r42", "ts": "2026-11-04T09:00:03Z", "tool": "edit_file", "target": "api/version.py"}
{"event": "tool_result", "session_id": "r42", "ts": "2026-11-04T09:00:04Z", "chars": 85}
```
