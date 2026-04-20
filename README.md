# adrift

A podcast source aggregation and reference alignment tool. It fetches podcast metadata from RSS feeds and YouTube, filters episodes, and merges matched reference/source entries into a canonical output set.

## Install Dependencies

### Node.js (Recommended for YouTube Downloads)

Node.js helps yt-dlp handle YouTube's metadata extraction edge cases and solve JavaScript challenges.

**Linux/WSL:**

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

**Windows:**
Download from [nodejs.org](https://nodejs.org/) or use:

```bash
choco install nodejs  # Using Chocolatey
# or
winget install OpenJS.NodeJS  # Using winget
```

**Verify installation:**

```bash
node --version
npm --version
```

## Install Poetry

This project uses [Poetry](https://python-poetry.org/) for dependency management.

**Install via the official installer:**

```bash
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

Then add `%APPDATA%\Python\Scripts` to your PATH (the installer will show the exact command).

## Working with the Virtual Environment
<!-- cspell:words venv -->

```bash
# Install all dependencies (creates .venv in the project folder)
poetry install --with dev

# Activate the virtual environment
.venv\Scripts\activate

# Or run a command directly without activating
poetry run python -m runbook.merge --pretty

# When done, deactivate
deactivate
```

## Update Dependencies

```bash
# Add a new dependency
poetry add <package>

# Add a dev-only dependency
poetry add --group dev <package>

# Update all packages to latest allowed versions
poetry update

# Show outdated packages
poetry show --outdated
```

## Project Structure

- `runbook/` - Main scripts (`merge.py` and project analysis helpers)
- `src/` - Core source code
  - `adapters/` - Source adapters for RSS and YouTube
  - `web/` - RSS feed parsing and serialization
  - `youtube/` - YouTube metadata extraction
  - `utils/` - Normalization, caching, and progress helpers
- `config/` - Podcast configurations in TOML format
- `tests/` - Unit tests

## Usage

Run the merge pipeline across one or more config files:

```bash
poetry run python -m runbook.merge --include config/*.toml --pretty
```

Useful options:

- `--skip-schedule-filter` to include podcasts even when their configured schedule does not match today.
- `--include-counts` to include reference and source counts alongside merged episodes.
- `--output-dir downloads` to write a navigable output bundle per config under `./downloads`.

When `--output-dir` is set, the merge run writes:

- `downloads/report.json` for the aggregate JSON report.
- `downloads/index.json` as a directory map from config to generated feed snapshots.
- `downloads/<slug>/config.json` for the resolved config.
- `downloads/<slug>/feeds/combined.json`, a single per-podcast JSON file containing the full `MergeResult` payload.

Note: the per-feed `references.json` and `downloads.json` files are no longer written by default; their contents are included in the `MergeResult` stored in `feeds/combined.json`.

## Secret Management

Use the secret-management TUI to inspect and update the required S3 settings stored in `.env`.

```bash
poetry run adrift-secrets
```

The first version manages these keys:

- `S3_USERNAME`
- `S3_SECRET_KEY`
- `S3_ENDPOINT`
- `S3_REGION`

Notes:

- Values written through the TUI are persisted to `.env`.
- The table masks sensitive values such as `S3_SECRET_KEY`.
- Validation can check either that required keys are present or that the configured S3 endpoint is reachable.
- Runtime secret-provider selection still uses `ADRIFT_SECRETS_PROVIDER`.
- The env-backed provider is writable through the TUI; non-env backends such as `docker` are inspect-only in the runbook today.
- Set `ADRIFT_SECRETS_PROMPT_FALLBACK=1` to let runtime reads prompt interactively for missing managed S3 keys instead of failing immediately. Leave it unset for automation and non-interactive runs.

## Containerized Download Run

The download pipeline can run in Docker via `compose.download.yaml` and `Dockerfile.download`.

Prerequisites:

- Docker with `docker compose`
- A populated `.env` file for S3 and other runtime settings
- Optional: a `cookies.txt` file if you need authenticated YouTube access from inside the container

Build and run:

```bash
make build
make download ARGS="--skip-download"
```

You can pass any `runbook/download.py` CLI flags through `ARGS`, for example `make download ARGS="--include config/youtube.toml --max-downloads 3"`.

The Makefile is the main Docker entrypoint:

```bash
make help
make merge ARGS="--include config/podcasts.toml --pretty"
```

Notes:

- The container persists `downloads/` and `.cache/` back to the host via bind mounts.
- `config/` is mounted read-only so local config edits are picked up without rebuilding.
- `LOCAL_S3_ENDPOINT` defaults to `http://host.docker.internal:9000` so a host-local MinIO/S3-compatible service remains reachable from the container.
- Browser-cookie discovery from Firefox will not work inside the container unless that browser profile is also mounted. For YouTube auth, prefer mounting a cookie file and setting `YT_COOKIES_FILE=/app/cookies.txt`.

## Configuration

Podcast series are defined in TOML files under `config/`:

| File | Contents |
| ------ | ---------- |
| `config/podcasts.toml` | RSS-first podcast series |
| `config/youtube.toml` | YouTube-first podcast series |

### Entry format

```toml
[[podcasts]]
title    = "My Podcast"
path     = "/media/podcasts/my-podcast"
feeds    = ["https://example.com/feed.rss"]
sources  = ["yt://@MyChannel"]
schedule = "FREQ=WEEKLY;BYDAY=WE,FR"   # download every Wed & Fri

[podcasts.filters]       # applied to both feeds and sources by default
exclude = ["bonus", "preview"]
include = []             # if non-empty, title must match at least one pattern

[podcasts.feed_filters]  # overrides filters for RSS feeds only (optional)
exclude = ["shorts"]

[podcasts.source_filters]  # overrides filters for sources only (optional)
include = ["My Podcast"]   # only grab videos with this title
```

### Filter rules

Each filter sub-table supports three fields. All patterns are Python
[`re.search`](https://docs.python.org/3/library/re.html#re.search)
patterns (case-insensitive):

| Field | Effect |
| ------- | -------- |
| `exclude` | Episode is **rejected** if its title matches *any* pattern. Prefix a pattern with `^` to anchor it at the start of the title. |
| `include` | When non-empty, episode is **rejected** unless its title matches *at least one* pattern. |
| `r_rules` | RFC 5545 RRULE strings; only keep episodes whose publish date matches any of the given recurrence rules (e.g. `"FREQ=WEEKLY;BYDAY=MO"` for Monday-only). |

### Schedule filter (RRULE)

The `schedule` field accepts a subset of the
[iCalendar RRULE](https://icalendar.org/iCalendar-RFC-5545/3-8-5-3-recurrence-rule.html)
format:

| Value | Meaning |
| ------- | --------- |
| `"FREQ=WEEKLY;BYDAY=WE,FR"` | Every Wednesday and Friday |
| `"FREQ=WEEKLY;BYDAY=MO"` | Every Monday |
| `"FREQ=WEEKLY"` | Once per week on a day derived deterministically from the show title |
| *(omitted)* | Include every time the script runs |

BYDAY codes: `MO` `TU` `WE` `TH` `FR` `SA` `SU`
