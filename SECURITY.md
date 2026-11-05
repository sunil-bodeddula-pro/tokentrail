# Security and privacy

## Reporting a vulnerability

Please report security problems privately through GitHub's **Report a vulnerability** button on the Security tab, not in a public issue. You'll get a reply within a week.

## What TokenTrail stores and sends

| Data | Local store | Remote mirror (default) |
| :--- | :--- | :--- |
| Prompt text and conversation titles | Yes | **No**: emptied before upload, run marked `redacted` |
| Token counts, models, tool names and counts, errors, timings | Yes | Yes |
| Workspace names and working directories | Yes | Yes |
| Commit subjects, authors and emails | Yes | Yes |
| File contents or tool output text | No (only sizes) | No |

- The dashboard binds to `127.0.0.1`. Binding it to another address (`--host`) exposes your prompts to that network.
- TokenTrail makes no network calls except to the remote you configure.
- Use a private bucket with access limited to the people who should see the data. `--keep-prompts-remote` uploads prompt text too; only use it for a bucket that only you can read.
- Credentials come from the standard Google Cloud and AWS credential chains. TokenTrail never stores them.
