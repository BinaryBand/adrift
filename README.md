# adrift

A podcast aggregation and ad-removal platform that downloads episodes from RSS feeds and YouTube, filters content, removes ads/sponsors, and manages custom RSS feeds with S3 storage.

## Install Dependencies

### FFmpeg (Required)

FFmpeg is required for audio processing and format conversion.

**Linux/WSL:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH, or use:

```bash
choco install ffmpeg  # Using Chocolatey
# or
winget install ffmpeg  # Using winget
```

### Node.js (Recommended for YouTube Downloads)

Node.js helps yt-dlp handle YouTube's bot detection and solve JavaScript challenges.

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

## Working with Virtual Environments

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install project dependencies
pip install -r requirements.txt

# When done, deactivate
deactivate
```

## Update Dependencies

```bash

# Install/update dependencies from requirements.txt
pip install -r requirements.txt

# To upgrade all packages to latest versions
pip install --upgrade -r requirements.txt

# To check for outdated packages
pip list --outdated
```

## Project Structure

- `runbook/` - Main scripts (`download.py`, `podcasts/`)
- `src/` - Core source code
  - `files/` - Audio processing, feature extraction, S3 operations
  - `web/` - RSS feed parsing, SponsorBlock integration
  - `youtube/` - YouTube downloading and metadata extraction
  - `utils/` - Logging, caching, progress tracking
- `config/` - Podcast configurations in TOML format
- `tests/` - Unit tests

## Configuration

Podcast series are defined in TOML files under `config/`:

| File | Contents |
|------|----------|
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

Each filter subtable supports three fields.  All patterns are Python
[`re.search`](https://docs.python.org/3/library/re.html#re.search)
patterns (case-insensitive):

| Field | Effect |
|-------|--------|
| `exclude` | Episode is **rejected** if its title matches *any* pattern. Prefix a pattern with `^` to anchor it at the start of the title. |
| `include` | When non-empty, episode is **rejected** unless its title matches *at least one* pattern. |
| `publish_days` | Only keep episodes published on the listed days (`"mon"` … `"sun"`). |

### Download schedule (RRULE)

The `schedule` field accepts a subset of the
[iCalendar RRULE](https://icalendar.org/iCalendar-RFC-5545/3-8-5-3-recurrence-rule.html)
format:

| Value | Meaning |
|-------|---------|
| `"FREQ=WEEKLY;BYDAY=WE,FR"` | Every Wednesday and Friday |
| `"FREQ=WEEKLY;BYDAY=MO"` | Every Monday |
| `"FREQ=WEEKLY"` | Once per week on a day derived deterministically from the show title |
| *(omitted)* | Download every time the script runs |

BYDAY codes: `MO` `TU` `WE` `TH` `FR` `SA` `SU`

