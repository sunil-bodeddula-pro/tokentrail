---
name: release
description: Cut a new TokenTrail release and publish it to PyPI. Use when the maintainer asks to release, publish, ship a version, bump the version, tag a release, or push a new version to PyPI. Covers choosing the version number, updating CHANGELOG.md, checks, creating the GitHub release that triggers the PyPI upload, verifying it, and what to do when the Release workflow fails.
---

# Releasing TokenTrail

Publishing a GitHub release tagged `vX.Y.Z` runs `.github/workflows/release.yml`, which uploads to PyPI through trusted publishing. No API token exists or is needed. **A version can never be re-uploaded to PyPI**, even after deleting it, so get the checks right before tagging.

## 1. Choose the version

The version lives only in `src/tokentrail/__init__.py` (`__version__`); `pyproject.toml` reads it from there. Follow semantic versioning:

| Change since the last release | Bump | Example |
| :--- | :--- | :--- |
| Bug fixes, docs, dashboard polish | Patch | 0.1.0 → 0.1.1 |
| New features, new adapters, new settings or flags (backwards compatible) | Minor | 0.1.1 → 0.2.0 |
| Breaking change to the CLI, config, HTTP API or store format | Major (minor while on 0.x) | 0.9.0 → 1.0.0 |

A store format change needs a new `v2/` directory and a migration (see AGENTS.md), and is always called out in the changelog.

List what changed since the last tag to decide:

```bash
git fetch --tags
git log --oneline "$(git describe --tags --abbrev=0)"..HEAD
```

If there's nothing user-visible since the last tag, say so and don't release.

## 2. Prepare the release commit

1. Set `__version__ = "X.Y.Z"` in `src/tokentrail/__init__.py`.
2. In `CHANGELOG.md`, move the items under **Unreleased** into a new `## [X.Y.Z] - YYYY-MM-DD` section, grouped as Added, Changed, Fixed and Security. Write for users ("`tokentrail pull` restores a wiped store"), not commit subjects. Update the compare links at the bottom.
3. Run every check CI runs:

   ```bash
   ruff check . && ruff format --check . && mypy
   python3 -m unittest discover -s tests -v
   ```

4. Commit as `Release X.Y.Z`, push to `main`, and wait for CI to pass on that commit (`gh run list --workflow ci.yml --limit 1`, then `gh run watch <id> --exit-status`).

## 3. Optional dry run on TestPyPI

Actions → **Release** → **Run workflow** (or `gh workflow run release.yml`) builds the package and uploads it to TestPyPI. This needs the TestPyPI trusted publisher (environment `testpypi`). Skip it for small patch releases.

## 4. Publish

**Ask the maintainer before this step.** Creating the release publishes to PyPI immediately and can't be undone. Show them the version and the changelog section, and wait for a clear yes.

```bash
awk -v v="X.Y.Z" '$0 ~ "^## \\[" v "\\]" {on=1; next} on && (/^## \[/ || /^\[/) {exit} on' CHANGELOG.md > /tmp/notes.md
gh release create vX.Y.Z --target main --title "TokenTrail X.Y.Z" --notes-file /tmp/notes.md
```

The tag must be `v` plus exactly the `__version__` string. The workflow refuses to publish otherwise.

If your permission mode blocks creating the release, give the maintainer the command to run themselves (with `!` in Claude Code) instead of looking for a way around it.

## 5. Verify

```bash
gh run watch "$(gh run list --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
curl -s https://pypi.org/pypi/tokentrail/json | python3 -c "import json,sys; i=json.load(sys.stdin)['info']; print(i['version'])"
python3 -m pip install --target /tmp/tt-check --no-cache-dir "tokentrail==X.Y.Z" && PYTHONPATH=/tmp/tt-check python3 -m tokentrail --version
```

Report the PyPI URL (https://pypi.org/project/tokentrail/X.Y.Z/) and the release URL. PyPI can take a minute to show the new version.

## When the Release workflow fails

| Failure | Cause | Fix |
| :--- | :--- | :--- |
| "Release tag … does not match __version__" | Tag and `__init__.py` disagree | Delete the release and tag (`gh release delete vX.Y.Z --cleanup-tag`), fix, and release again. Nothing reached PyPI |
| Tests or `twine check` fail in `build` | Broken code or package metadata | Same as above: nothing was uploaded |
| `invalid-publisher` or a trusted publishing error in `pypi` | PyPI's publisher settings don't match | On pypi.org → project → Publishing, the values must be owner `sunil-bodeddula-pro`, repo `tokentrail`, workflow `release.yml`, environment `pypi`. Fix them, then re-run the failed job: `gh run rerun <id> --failed` |
| "Deployment … not allowed" for the `pypi` environment | The run didn't come from a `v*` tag | Publish from a release tag, never from a branch |
| "File already exists" | That version is already on PyPI | Bump to the next patch version; versions can't be reused |

Never edit the workflow to skip the version check or the tests in order to get a release out.
