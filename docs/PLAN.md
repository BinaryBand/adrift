# Plan: Merge live code with SPECS.md logic

## Context

The codebase is a working but organically grown Python podcast pipeline. The spec in `docs/SPECS.md` formalizes a cleaner architecture for the same domain. The goal is to adopt the spec's better-designed abstractions — particularly the config model, cross-alignment algorithm, and merge rules — while keeping the working download/S3/ffmpeg infrastructure untouched.

Key improvements from the spec:
1. **Cleaner config model**: `references`/`downloads` as `FeedSource` objects with per-source filters, vs. flat `feeds`/`sources` lists with awkward dict-based per-source overrides.
2. **Richer matching**: Weighted 4-signal scorer (ID + date + title + description) vs. title-only fuzzy matching for cross-aligning reference and download episode lists.
3. **Explicit merge rules**: Field-level resolution when combining reference + download episodes.

---

## Critical files

| File | Role |
|---|---|
| `src/app_common.py` | Config models — `PodcastData`, `FilterRules`, `load_podcasts_config` |
| `src/catalog.py` | Episode matching/alignment — `match()`, `process_feeds()`, `process_sources()` |
| `src/models/metadata.py` | Data models — `RssEpisode`, `RssChannel` |
| `runbook/podcasts/update_podcasts.py` | Feed generation runbook |
| `runbook/podcasts/download_podcasts.py` | Audio download runbook |
| `config/podcasts.toml`, `config/youtube.toml` | TOML podcast configs |
| `tests/misc/test_podcast_configs.py` | Config validation tests |
| `tests/misc/test_filter_rules.py` | FilterRules tests |

---

## Phase 1 — Config model refactor (`src/app_common.py`)

### 1a. Introduce `SourceFilter` and `FeedSource`

Replace `FilterRules` with `SourceFilter` (same fields: `include`, `exclude`, `publish_days`; same `to_regex()` logic — just renamed). Add `FeedSource`:

```python
class SourceFilter(BaseModel):
    include: list[str] = []
    exclude: list[str] = []
    publish_days: list[DAY_OF_WEEK] = []

    def to_regex(self) -> str | None: ...  # same logic as FilterRules.to_regex()

class FeedSource(BaseModel):
    url: str
    filters: SourceFilter = SourceFilter()
```

Keep `FilterRules = SourceFilter` as an alias to avoid breaking tests.

### 1b. Rename `PodcastData` → `PodcastConfig`

New fields: `name` (alias `title`), `references: list[FeedSource]`, `downloads: list[FeedSource]`, `schedule: list[str]`.

Add a `model_validator(mode="before")` backward-compat shim that maps old flat TOML fields:
- `"title"` → `"name"`
- `"feeds": [url, ...]` + `"filters"/"feed_filters"` → `"references": [FeedSource(url, filters), ...]`
- `"sources": [url, ...]` + `"filters"/"source_filters"` → `"downloads": [FeedSource(url, filters), ...]`
- `"schedule": str` → `"schedule": [str]`

Add `title` property returning `self.name` so all call sites stay compatible.

### 1c. Update `_schedule_matches_today` and `load_podcasts_config`

`_schedule_matches_today` now iterates `config.schedule` (a `list[str]`). Empty list = no schedule = always run.

---

## Phase 2 — Output models (`src/models/output.py` — new file)

```python
class EpisodeData(BaseModel):
    id: str
    title: str
    description: str
    source: list[str]          # union of source URLs
    thumbnail: str | None = None
    upload_date: datetime | None = None

class PodcastFeed(BaseModel):  # avoids collision with existing PodcastData config name
    id: str
    title: str
    author: str
    description: str
    source: str
    thumbnail: str | None = None
    episodes: list[EpisodeData] = []
```

Export from `src/models/__init__.py`. Keep `RssEpisode` and `RssChannel` untouched — they remain the internal RSS layer types.

> **Naming note**: The spec calls the output `PodcastData`, but that name is already taken by the config model (being renamed to `PodcastConfig`). Use `PodcastFeed` for the output to avoid confusion during the migration.

---

## Phase 3 — New alignment algorithm (`src/catalog.py`)

### 3a. Add `sim_date()`

```python
def sim_date(a: datetime | None, b: datetime | None) -> float:
    if a is None or b is None: return 0.0
    delta = abs((a - b).days)
    if delta <= 2:  return 1.00
    if delta <= 10: return 0.70
    if delta <= 35: return 0.15
    return 0.00
```

### 3b. Add `align_episodes()`

Replaces the cross-list matching in `process_feeds()`. Takes `references: list[RssEpisode]` and `downloads: list[RssEpisode]`. Uses spec weights:

```
W_ID=0.10, W_DATE=0.30, W_TITLE=0.50, W_DESC=0.10, θ=MATCH_TOLERANCE(0.75)

score = W_ID*sim_id + W_DATE*sim_date + W_TITLE*sim_title + W_DESC*sim_desc
```

Where:
- `sim_id`: binary `1.0` if `ref.id == dl.id`, else `0.0`
- `sim_date`: `sim_date(ref.pub_date, dl.pub_date)`
- `sim_title`: `_similarity_clean(normalize_text(ref.title), normalize_text(dl.title))` (reuses existing helper)
- `sim_desc`: `_similarity_clean(normalize_text(ref.description or ""), normalize_text(dl.description or ""))`

Greedy matching is identical to existing `match()`. Returns `list[tuple[int, int]]`.

### 3c. Add `merge_episode()`

```python
def merge_episode(ref: RssEpisode, dl: RssEpisode) -> EpisodeData:
    # id: prefer non-URL id (YouTube IDs are short alphanumeric; RSS GUIDs are often URLs)
    id = ref.id if not ref.id.startswith("http") else dl.id
    title = max([ref.title, dl.title], key=lambda t: (len(t), t.count(":")))
    upload_date = min(filter(None, [ref.pub_date, dl.pub_date]), default=None)
    description = max([ref.description or "", dl.description or ""], key=len) or ""
    thumbnail = _best_thumbnail(ref.image, dl.image)
    source = list({u for u in [ref.content, dl.content] if u})
    return EpisodeData(id=id, title=title, description=description,
                       source=source, thumbnail=thumbnail, upload_date=upload_date)
```

`_best_thumbnail`: rank by resolution keyword in URL (`maxres` > `hq` > `mq` > `sq` > default).

### 3d. Refactor `process_feeds()` / `process_sources()` → `_collect_episodes()`

Single function replacing both:

```python
def _collect_episodes(
    sources: list[FeedSource],
    title: str,
    is_reference: bool,
    callback: Callback | None = None,
) -> list[RssEpisode]:
```

Iterates `FeedSource` objects instead of bare URLs, uses `fs.filters.to_regex()` and `fs.filters.publish_days`. Deduplicates across multiple same-side sources using existing title-only `match()` (appropriate since these are same-platform episodes).

Keep `process_feeds()` and `process_sources()` as thin wrappers calling `_collect_episodes(config.references, ...)` and `_collect_episodes(config.downloads, ...)` so runbooks need minimal changes.

### 3e. Update `process_channel()`

Change `for feed_url in config.feeds:` → `for fs in config.references: feed_url = fs.url`.

---

## Phase 4 — Runbook updates

### `runbook/podcasts/update_podcasts.py`

`update_series(config: PodcastConfig)` — rename parameter type only. Body stays the same because `process_feeds`/`process_sources` wrappers are preserved. The file→episode `match()` step is kept as-is (title-only is correct here — matching S3 filenames to episode titles, not cross-platform episodes).

### `runbook/podcasts/download_podcasts.py`

Change `config.sources` → `[fs.url for fs in config.downloads]` in the download loop. The `.title` property means `config.title` still works.

### `runbook/validate_configs.py`

`PodcastData` → `PodcastConfig` in import and usage.

---

## Phase 5 — TOML migration (`config/podcasts.toml`, `config/youtube.toml`)

Migrate all entries from flat format to new nested format. The backward-compat shim (Phase 1b) means the system keeps working before and after.

Old:
```toml
[[podcasts]]
title = "Behind the Bastards"
path  = "/media/podcasts/behind-the-bastards"
feeds = ["https://...rss"]
sources = ["yt://@BehindTheBastards"]
schedule = "FREQ=WEEKLY;BYDAY=WE,FR"
```

New:
```toml
[[podcasts]]
name = "Behind the Bastards"
path = "/media/podcasts/behind-the-bastards"
schedule = ["FREQ=WEEKLY;BYDAY=WE,FR"]

[[podcasts.references]]
url = "https://...rss"

[[podcasts.downloads]]
url = "yt://@BehindTheBastards"
```

For shows with per-side filters, attach `[podcasts.references.filters]` / `[podcasts.downloads.filters]` under their respective `[[...]]` block.

After all TOML files are migrated, remove the `_migrate_legacy_fields` validator from `PodcastConfig`.

---

## Phase 6 — Test updates

### Files to update in-place

- `tests/misc/test_podcast_configs.py`: `PodcastData` → `PodcastConfig`, `podcast.feeds` → `[fs.url for fs in podcast.references]`, `podcast.sources` → `[fs.url for fs in podcast.downloads]`, schedule assertion updated for list type.
- `tests/misc/test_filter_rules.py`: `FilterRules` → `SourceFilter` (or keep alias — both work).

### New test file: `tests/misc/test_align_episodes.py`

Cover:
- `sim_date()` — each tier, `None` inputs
- `_weighted_score()` — cross-platform pair (sim_id=0), same-platform pair (sim_id=1)
- `align_episodes()` — basic match, greedy tie-breaking, threshold cutoff
- `merge_episode()` — ID preference, title longest-wins, description longest-wins, earliest date, source union

---

## What stays untouched

- `src/files/` — audio processing, S3 operations
- `src/web/rss.py` — RSS parsing and XML generation
- `src/youtube/` — yt-dlp download stack
- `src/utils/` — text normalization, cache, crypto
- `similarity()` / `_similarity_clean()` in `catalog.py` — reused as `sim_title`/`sim_desc`
- `match()` greedy algorithm — kept for file↔episode (S3 filename) matching
- `normalize_title()` show-specific cleaners in `app_runner.py`
- RSS XML output format

---

## Execution order (dependencies)

```
Phase 1 (app_common.py)
├── Phase 5 (TOML migration) — can run any time after Phase 1
└── Phase 2 (output.py) — can run in parallel with Phase 1
         ↓
    Phase 3 (catalog.py new matcher)
         ↓
    Phase 4 (runbook updates)
         ↓
    Phase 6 (tests)
```

---

## Verification

1. `python runbook/validate_configs.py` — all TOML entries load cleanly under new schema
2. `pytest tests/` — existing tests pass; new `test_align_episodes.py` passes
3. `mypy src/ runbook/` — no new type errors
4. Dry-run download for one podcast: `python runbook/download.py --include podcasts` — completes without errors, uploads correct `feed.rss` to S3
