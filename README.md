# adrift

**Merge podcast episodes from multiple sources (RSS, YouTube) and find matches.**

adrift aligns your reference episodes (what you want) with your download sources (where to get it), and outputs a unified feed. It's like a deduplication and reconciliation tool for podcast pipelines.

## 5-Minute Quickstart

### 1. Install Python & uv

- **Python 3.11+**: [python.org](https://www.python.org/)
- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### 2. Clone & Set Up

```bash
git clone <repo>
cd adrift
uv sync --all-groups
```

### 3. Run Your First Merge

```bash
uv run adrift-merge --include 'static/config/podcasts.toml' --pretty
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
Result:    -> Merged as one episode with both metadata sources
```

---

## Configuration

Create TOML files in `static/config/`:

```toml
[[podcasts]]
name     = "My Show"
path     = "/media/podcasts/my-show"             # Storage bucket/prefix
schedule = ["FREQ=WEEKLY;BYDAY=WE,FR"]           # Optional: download on Wed/Fri

[[podcasts.references]]
url = "https://example.com/rss"                  # Reference episodes (metadata)
[podcasts.references.filters]
exclude = ["bonus", "clip"]                      # Skip these titles
include = []                                     # If set, title must match one

[[podcasts.downloads]]
url = "yt://@MyChannel"                          # Download sources (files)
```

| Schedule | Meaning |
| ---------- | --------- |
| `FREQ=WEEKLY;BYDAY=MO` | Every Monday |
| `FREQ=WEEKLY;BYDAY=WE,FR` | Every Wed & Fri |
| *(omitted)* | Every run |

See `static/config/podcasts.toml` and `static/config/youtube.toml` for examples.

---

## Common Commands

```bash
# Basic merge, pretty-printed
uv run adrift-merge --include 'static/config/*.toml' --pretty

# Include episode counts
uv run adrift-merge --include 'static/config/podcasts.toml' --include-counts

# Save output to files (creates downloads/ directory)
uv run adrift-merge --include 'static/config/*.toml' --output-dir downloads

# Output performance metrics
uv run adrift-merge --include 'static/config/*.toml' --timings

# Download episodes (not just merge)
uv run adrift-download --include 'static/config/*.toml' --max-downloads 5
```

---

## Project Layout

```text
adrift/
|-- cli/              # Commands (merge, download, schema)
|-- services/         # Core logic (merge, download, alignment)
|-- models/          # Data structures
|-- adapters/        # RSS & YouTube fetchers
`-- utils/           # Helpers (profiler, cache, progress)
static/config/              # Your podcast configs (TOML)
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

### Working with uv

```bash
# Install dependencies
uv sync --all-groups

# Run command directly
uv run adrift-merge --help

# Activate venv for shell
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Add a dependency
uv add some-package
uv add --group dev some-dev-package

# Update packages
uv lock --upgrade && uv sync --all-groups
```

### Profiling

Enable function-level timing to find bottlenecks:

```bash
uv run adrift-merge --include 'static/config/*.toml' --timings
```

Outputs both per-podcast stage timings and a full profiling report showing which functions took the most time.

---

## Development

```bash
# Run tests
uv run pytest

# Lint, format, and all other quality gates (also runnable via pytest tests/test_lint.py)
uv run ruff check adrift tests
uv run ruff format --check adrift tests
uv run ty check --project .
uv run python -m vulture adrift tests --min-confidence 80
uv run python -m lizard adrift -x 'adrift/cli/*' -C 8 -L 30 -a 9
```

### Performance benchmarks

Benchmarks live in `tests/benchmarks/` and are skipped by default. They run
offline and cover:

| Benchmark | What is timed |
| --- | --- |
| `alignment.50x50` | Scoring kernel: 50 refs x 50 downloads |
| `alignment.150x150` | Scoring kernel: 150 refs x 150 downloads |
| `normalize_title.cold` | 300 titles, no caches warm |
| `normalize_title.warm_disk` | 300 titles, disk cache warm, LRU empty |

Baselines are stored as CPU-normalized values in
`tests/benchmarks/baselines.json` so the same file works across machines.

```bash
# Record baselines (run once on your machine after a performance change):
RECORD_PERF_BASELINE=1 uv run pytest tests/benchmarks/

# Enforce baselines -- fails if any benchmark exceeds 2x its recorded median:
RUN_PERF_TESTS=1 uv run pytest tests/benchmarks/

# Relax the threshold (e.g. on a slower CI machine):
PERF_TOLERANCE=3.0 RUN_PERF_TESTS=1 uv run pytest tests/benchmarks/
```

---

## Need More?

- Filter syntax: Python `re.search` patterns (case-insensitive)
- Alignment details: See [docs/DESIGN.md](docs/DESIGN.md)
- Contributing: See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- Architecture: See [docs/SPECS.md](docs/SPECS.md)
