# adrift

**Merge podcast episodes from multiple sources (RSS, YouTube) and find matches.**

adrift aligns your reference episodes (what you want) with your download sources (where to get it), and outputs a unified feed. It's like a deduplication and reconciliation tool for podcast pipelines.

## 5-Minute Quickstart

### 1. Install Python & Poetry

- **Python 3.11+**: [python.org](https://www.python.org/)
- **Poetry**: `curl -sSL https://install.python-poetry.org | python3 -`

### 2. Clone & Set Up

```bash
git clone <repo>
cd adrift
poetry install --with dev
```

### 3. Run Your First Merge

```bash
poetry run adrift-merge --include 'config/podcasts.toml' --pretty
```

That's it! The output is JSON printed to stdout. Add `--output-dir downloads` to save results to disk.

---

## What Does It Do?

**Input:** Podcast reference feeds (RSS/YouTube) + download sources  
**Process:** Fetch episodes, filter by title/date, match similar titles  
**Output:** Aligned episodes with metadata merged  

Example:

```text
Reference: "Episode 42: The Big One"
Download:  "S03E42 The Big One [HD]"
Result:    → Merged as one episode with both metadata sources
```

---

## Configuration

Create TOML files in `config/`:

```toml
[[podcasts]]
title    = "My Show"
feeds    = ["https://example.com/rss"]           # Reference episodes
sources  = ["yt://@MyChannel"]                   # Download sources
schedule = "FREQ=WEEKLY;BYDAY=WE,FR"            # Optional: download on Wed/Fri

[podcasts.filters]
exclude = ["bonus", "clip"]                      # Skip these titles
include = []                                     # If set, title must match one
```

| Schedule | Meaning |
| ---------- | --------- |
| `FREQ=WEEKLY;BYDAY=MO` | Every Monday |
| `FREQ=WEEKLY;BYDAY=WE,FR` | Every Wed & Fri |
| *(omitted)* | Every run |

See `config/podcasts.toml` and `config/youtube.toml` for examples.

---

## Common Commands

```bash
# Basic merge, pretty-printed
poetry run adrift-merge --include 'config/*.toml' --pretty

# Include episode counts
poetry run adrift-merge --include 'config/podcasts.toml' --include-counts

# Save output to files (creates downloads/ directory)
poetry run adrift-merge --include 'config/*.toml' --output-dir downloads

# Output performance metrics
poetry run adrift-merge --include 'config/*.toml' --timings

# Download episodes (not just merge)
poetry run adrift-download --include 'config/*.toml' --max-downloads 5
```

---

## Secrets (.env)

If you use S3 storage, create `.env`:

```text
S3_USERNAME=your_user
S3_SECRET_KEY=your_key
S3_ENDPOINT=https://s3.example.com
S3_REGION=us-east-1
```

---

## Project Layout

```text
adrift/
├── cli/              # Commands (merge, download, schema)
├── services/         # Core logic (merge, download, alignment)
├── models/          # Data structures
├── adapters/        # RSS & YouTube fetchers
└── utils/           # Helpers (profiler, cache, progress)
config/              # Your podcast configs (TOML)
tests/               # Unit tests
```

---

## Advanced Setup

### Node.js (for YouTube)

YouTube metadata extraction is more robust with Node.js installed:

**Linux/WSL:**

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

**Windows:** Download from [nodejs.org](https://nodejs.org/) or `choco install nodejs`

### Working with Poetry

```bash
# Install dependencies
poetry install --with dev

# Run command directly
poetry run adrift-merge --help

# Activate venv for shell
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Add a dependency
poetry add some-package
poetry add --group dev some-dev-package

# Update packages
poetry update
```

### Profiling

Enable function-level timing to find bottlenecks:

```bash
poetry run adrift-merge --include 'config/*.toml' --timings
```

Outputs both per-podcast stage timings and a full profiling report showing which functions took the most time.

---

## Development

```bash
# Run tests
poetry run pytest

# Lint & format
poetry run ruff check adrift/
poetry run mypy adrift/

# Type stubs & code complexity
poetry run ty check --project .
poetry run lizard adrift/
```

---

## Need More?

- Filter syntax: Python `re.search` patterns (case-insensitive)
- Alignment details: See [docs/DESIGN.md](docs/DESIGN.md)
- Contributing: See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- Architecture: See [docs/SPECS.md](docs/SPECS.md)
