# Changelog

All notable changes to TokenTrail. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

### Changed

- The session explorer is paginated: First, Prev, page numbers, Next and Last, with 10, 25, 50 or 100 rows per page. This replaces the Show more button.

## [0.1.0] - 2026-11-05

First public release.

### Added

- Reads Claude Code sessions out of the box. Any other agent can write the generic JSON-lines event format, or add an adapter.
- A durable store of plain JSON files, synced every 30 seconds (`--sync-interval` to change it). Data is kept when agent history is cleared, and unchanged files are never parsed twice.
- Optional mirror to `gs://`, `s3://` or a folder, with prompt text redacted before upload. `tokentrail pull` brings in other machines' data and restores a wiped store.
- A local dashboard: six KPIs, ten charts, a session explorer and inspector, Code Deliverables from git history, and Cross-Domain ROI.
- Commands: `init`, `dashboard`, `daemon`, `sync`, `pull`, `status`, `summary`, `export` and `service` (systemd, launchd or Task Scheduler).
- `examples/demo_data.py` writes a month of made-up sessions, so you can try the dashboard without an agent.
- No runtime dependencies. The `gcs` and `s3` extras add the cloud mirror clients.

[Unreleased]: https://github.com/sunil-bodeddula-pro/tokentrail/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sunil-bodeddula-pro/tokentrail/releases/tag/v0.1.0
